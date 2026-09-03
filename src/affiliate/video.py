"""Clip renderers.

Two interchangeable makers behind one interface:

* :class:`FfmpegVideoMaker` — works today with no API key: a slow push-in on
  the product photo with the script beats burned on.
* :class:`AIVideoMaker` — a generic image-to-video HTTP adapter. Endpoint,
  headers, payload and the response fields are all declared in
  ``config/affiliate.yaml``, so any vendor can be wired up without code.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import string
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any, Protocol

from .script import DURATION, ClipScript

log = logging.getLogger(__name__)

WIDTH, HEIGHT, FPS = 1080, 1920, 30

# Poll statuses, when a vendor block does not override them. Both spellings of
# "cancel*ed" are here because Replicate uses the American one.
DEFAULT_DONE_VALUES = ("succeeded", "completed", "done")
DEFAULT_FAILED_VALUES = ("failed", "error", "canceled", "cancelled")

# Fonts that can actually render Thai, in the order we try them.
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
    "/usr/share/fonts/truetype/tlwg/Loma.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Thonburi.ttc",
]


class VideoError(RuntimeError):
    """Rendering failed; the message is safe to show the user."""


class VideoMaker(Protocol):
    name: str
    # True when a render takes long enough that the caller should submit it,
    # persist a handle and poll later instead of blocking.
    is_async: bool

    def render(self, image_path: str, script: ClipScript, out_path: str) -> str:
        ...


# --- ffmpeg ---------------------------------------------------------------


class FfmpegVideoMaker:
    """Ken-Burns push-in on a still, with the four beats overlaid."""

    name = "ffmpeg"
    is_async = False   # local encode, a few seconds

    def __init__(self, font_path: str | None = None, burn_text: bool = True,
                 duration: float = DURATION):
        self.font_path = font_path or _find_font()
        self.burn_text = burn_text
        self.duration = duration

    def render(self, image_path: str, script: ClipScript, out_path: str) -> str:
        if not shutil.which("ffmpeg"):
            raise VideoError("ffmpeg not installed — install it or switch to the ai provider")
        if not os.path.exists(image_path):
            raise VideoError(f"source image missing: {image_path}")
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

        frames = int(self.duration * FPS)
        chain = [
            f"scale={WIDTH * 2}:{HEIGHT * 2}:force_original_aspect_ratio=increase",
            f"crop={WIDTH * 2}:{HEIGHT * 2}",
            # zoompan works on the upscaled frame so the push-in stays sharp.
            f"zoompan=z='min(zoom+0.0012,1.20)':d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS}",
            "format=yuv420p",
        ]
        overlay = self._text_filters(script) if self.burn_text else []
        if overlay:
            chain.extend(overlay)

        try:
            return self._encode(chain, image_path, out_path)
        except VideoError:
            if not overlay:
                raise
            # drawtext needs an ffmpeg built with libfreetype; fall back to a
            # clean clip rather than failing the whole job.
            log.warning("drawtext failed; re-rendering without burned text")
            return self._encode(chain[:-len(overlay)], image_path, out_path)

    def _encode(self, chain: list[str], image_path: str, out_path: str) -> str:
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", image_path,
            "-t", f"{self.duration:g}",
            "-vf", ",".join(chain),
            "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or not os.path.exists(out_path):
            tail = proc.stderr.strip().splitlines()[-3:]
            raise VideoError("ffmpeg failed: " + " / ".join(tail))
        return out_path

    def _text_filters(self, script: ClipScript) -> list[str]:
        thai = any(_has_thai(text) for _, _, text in script.lines())
        if thai and not _renders_thai(self.font_path):
            log.warning("no Thai-capable font at %s; rendering clip without burned "
                        "text (set affiliate.video.ffmpeg.font_path)", self.font_path)
            return []
        filters = []
        for index, (start, end, text) in enumerate(script.lines()):
            # Hook sits high, CTA low, the middle beats centred.
            y = {0: "h*0.16", 3: "h*0.74"}.get(index, "h*0.45")
            filters.append(
                f"drawtext=fontfile='{self.font_path}':text='{_escape(text)}'"
                f":fontcolor=white:fontsize=64:borderw=6:bordercolor=black@0.85"
                f":x=(w-text_w)/2:y={y}:enable='between(t,{start},{end})'"
            )
        return filters


def _escape(text: str) -> str:
    """Escape a string for ffmpeg's drawtext ``text=`` option."""
    out = text.replace("\\", "\\\\").replace("'", "’")
    for ch in (":", "%", ",", "[", "]", ";"):
        out = out.replace(ch, "\\" + ch)
    return out


def _find_font() -> str | None:
    return next((p for p in FONT_CANDIDATES if os.path.exists(p)), None)


# DejaVu resolves on almost every Linux box but has no Thai glyphs, so text
# burned with it comes out as tofu boxes.
_NON_THAI_FONTS = ("dejavu",)


def _renders_thai(font_path: str | None) -> bool:
    return bool(font_path) and not any(n in font_path.lower() for n in _NON_THAI_FONTS)


def _has_thai(text: str) -> bool:
    return any("\u0e00" <= ch <= "\u0e7f" for ch in text)


# --- generic AI image-to-video -------------------------------------------


class AIVideoMaker:
    """Config-driven image-to-video adapter (submit, then optionally poll)."""

    name = "ai"
    is_async = True    # vendors take 1-5 minutes per clip

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg or {}
        self.timeout = int(self.cfg.get("http_timeout_s", 60))

    @property
    def configured(self) -> bool:
        """Usable only if the endpoint is set AND every ${VAR} in it resolved.

        ``safe_substitute`` leaves an unset placeholder verbatim, so a missing
        API key would otherwise surface as a confusing 401 mid-render.
        """
        url = _expand(self.cfg.get("submit_url", ""))
        if not url or "${" in url:
            return False
        return not any("${" in value for value in self._headers().values())

    def render(self, image_path: str, script: ClipScript, out_path: str) -> str:
        """Blocking render — used by the CLI and selftest.

        The bot uses submit/poll_once/fetch instead so a slow generation does
        not hold up every other job in the batch.
        """
        handle = self.submit(image_path, script)
        deadline = time.time() + float(self.cfg.get("poll_timeout_s", 300))
        while True:
            url = self.poll_once(handle)
            if url:
                return self.fetch(url, out_path)
            if time.time() >= deadline:
                raise VideoError("timed out waiting for the provider to render the clip")
            time.sleep(float(self.cfg.get("poll_interval_s", 5)))

    def submit(self, image_path: str, script: ClipScript) -> dict[str, Any]:
        """Start a generation. Returns a small JSON-serialisable handle."""
        if not self.configured:
            raise VideoError(
                "no image-to-video endpoint configured — set affiliate.video.ai."
                "submit_url (and its api key env var) in config/affiliate.yaml"
            )
        fields = {
            "prompt": self.prompt(script),
            "image_b64": base64.b64encode(self._prepare_image(image_path)).decode(),
            "duration": str(self.cfg.get("duration", int(DURATION))),
        }
        submitted = self._post(_expand(self.cfg["submit_url"]),
                               _fill(self.cfg.get("payload", {}), fields))
        url = _dig(submitted, self.cfg.get("result_path", "video_url"))
        job_id = _dig(submitted, self.cfg.get("job_id_path", "id"))
        if not url and not job_id:
            raise VideoError("provider returned neither a video url nor a job id "
                             "— check video.ai.result_path / job_id_path")
        return {"job_id": str(job_id or ""), "video_url": str(url) if url else None}

    def poll_once(self, handle: dict[str, Any]) -> str | None:
        """One non-blocking check. Returns the video url, or None if pending."""
        if handle.get("video_url"):
            return str(handle["video_url"])
        if not self.cfg.get("poll_url"):
            raise VideoError("provider gave no video url on submit and no "
                             "video.ai.poll_url is configured")
        url = _expand(self.cfg["poll_url"]).replace("{job_id}",
                                                    str(handle.get("job_id", "")))
        payload = self._get(url)
        status = str(_dig(payload, self.cfg.get("poll_status_path", "status")) or "").lower()
        if status and status in {str(v).lower() for v in
                                 self.cfg.get("poll_failed_values", DEFAULT_FAILED_VALUES)}:
            raise VideoError(f"provider reported status '{status}'")
        done = {str(v).lower()
                for v in self.cfg.get("poll_done_values", DEFAULT_DONE_VALUES)}
        if status and status in done:
            payload = self._fetch_result(payload)
        video = _dig(payload, self.cfg.get("result_path", "video_url"))
        if video and (not status or status in done):
            return str(video)
        return None

    def fetch(self, url: str, out_path: str) -> str:
        """Download a finished clip."""
        return self._download(url, out_path)

    def _fetch_result(self, status_payload: Any) -> Any:
        """Second hop for queue APIs whose status response omits the output.

        fal.ai is the common case: /status carries `status` but the artefacts
        live at a separate result URL.
        """
        template = self.cfg.get("result_url")
        if not template:
            return status_payload
        url = _expand(template)
        for key, path in (("job_id", self.cfg.get("job_id_path", "id")),
                          ("result_id", self.cfg.get("result_id_path", ""))):
            if path and "{" + key + "}" in url:
                url = url.replace("{" + key + "}", str(_dig(status_payload, path) or ""))
        return self._get(url)

    def _prepare_image(self, image_path: str) -> bytes:
        """Shrink the photo if it would exceed the vendor's data-URI limit.

        Replicate recommends staying under 1MB; Runway hard-rejects over ~5MB
        encoded. Base64 inflates by ~4/3, so the cap is on the raw bytes.
        """
        limit = int(self.cfg.get("max_image_bytes", 1_000_000))
        with open(image_path, "rb") as fh:
            raw = fh.read()
        if not limit or len(raw) <= limit:
            return raw
        if not shutil.which("ffmpeg"):
            log.warning("image is %d bytes (limit %d) and ffmpeg is unavailable to "
                        "resize it; sending as-is", len(raw), limit)
            return raw
        small = os.path.join(os.path.dirname(image_path) or ".", "source_small.jpg")
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", image_path,
             "-vf", "scale='min(1080,iw)':-2", "-q:v", "6", small],
            capture_output=True, text=True)
        if proc.returncode != 0 or not os.path.exists(small):
            log.warning("could not downscale %s; sending as-is", image_path)
            return raw
        with open(small, "rb") as fh:
            return fh.read()

    def prompt(self, script: ClipScript) -> str:
        template = self.cfg.get(
            "prompt",
            "8-second vertical product video, {hook}. Slow cinematic push-in on the "
            "product, soft studio light, clean background, no text overlay.",
        )
        return template.format(hook=script.hook, benefit=script.benefit,
                               price=script.price, cta=script.cta)

    # --- transport -------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        base = {"Content-Type": "application/json"}
        for key, value in (self.cfg.get("headers") or {}).items():
            base[key] = _expand(str(value))
        return base

    def _post(self, url: str, payload: dict[str, Any]) -> Any:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers=self._headers(), method="POST")
        return self._send(req)

    def _get(self, url: str) -> Any:
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        return self._send(req)

    def _send(self, req: urllib.request.Request) -> Any:
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            raise VideoError(f"provider HTTP {exc.code}: "
                             f"{exc.read().decode(errors='replace')[:300]}") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise VideoError(f"provider call failed: {exc}") from exc

    def _download(self, url: str, out_path: str) -> str:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        # Public CDN links need no auth, but some vendors gate the artefact
        # behind the same key as the API.
        headers = self._headers() if self.cfg.get("authenticated_download") else {}
        headers.pop("Content-Type", None)
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp, \
                    open(out_path, "wb") as fh:
                shutil.copyfileobj(resp, fh)
        except OSError as exc:
            raise VideoError(f"could not download the rendered clip: {exc}") from exc
        return out_path


def _expand(value: str) -> str:
    """Resolve ``${ENV_VAR}`` references so secrets stay out of the YAML."""
    return string.Template(value).safe_substitute(os.environ) if value else value


def _fill(payload: Any, fields: dict[str, str]) -> Any:
    """Recursively substitute ``{prompt}`` / ``{image_b64}`` / ``{duration}``."""
    if isinstance(payload, dict):
        return {k: _fill(v, fields) for k, v in payload.items()}
    if isinstance(payload, list):
        return [_fill(v, fields) for v in payload]
    if isinstance(payload, str):
        out = _expand(payload)
        for key, value in fields.items():
            out = out.replace("{" + key + "}", value)
        return out
    return payload


def _dig(payload: Any, path: str) -> Any:
    """Follow a dotted path such as ``data.output.0.url`` through a JSON blob."""
    node = payload
    for part in str(path).split("."):
        if isinstance(node, dict):
            node = node.get(part)
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return None
    return node


def make(cfg: dict[str, Any]) -> VideoMaker:
    """Build the maker named by ``affiliate.video.provider``.

    ``ai`` falls back to ffmpeg when no endpoint is configured, so the pipeline
    still produces a clip before the API key arrives.
    """
    video_cfg = cfg or {}
    provider = str(video_cfg.get("provider", "ffmpeg")).lower()
    if provider == "ai":
        maker = AIVideoMaker(video_cfg.get("ai", {}))
        if maker.configured:
            return maker
        log.warning("video.provider=ai but submit_url or an API key is missing "
                    "— falling back to ffmpeg")
    ffmpeg_cfg = video_cfg.get("ffmpeg", {}) or {}
    return FfmpegVideoMaker(
        font_path=ffmpeg_cfg.get("font_path"),
        burn_text=bool(ffmpeg_cfg.get("burn_text", True)),
        duration=float(video_cfg.get("duration", DURATION)),
    )
