"""Minimal Telegram Bot API client (stdlib only).

Long-polls ``getUpdates`` and sends text / photo / video with inline keyboards.
``requests`` is deliberately avoided so the bot adds no new dependency.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

API_ROOT = "https://api.telegram.org"


class TelegramError(RuntimeError):
    """Telegram replied with ``ok: false`` or the transport failed."""


@dataclass
class Button:
    """One inline-keyboard button. ``data`` is echoed back in a callback query."""

    text: str
    data: str


def keyboard(*rows: list[Button]) -> dict[str, Any]:
    """Build an inline keyboard markup from rows of buttons."""
    return {
        "inline_keyboard": [
            [{"text": b.text, "callback_data": b.data} for b in row] for row in rows
        ]
    }


@dataclass
class Update:
    """The few Telegram update fields this bot actually acts on."""

    update_id: int
    chat_id: int | None = None
    text: str | None = None
    photo_file_id: str | None = None
    callback_data: str | None = None
    callback_id: str | None = None
    message_id: int | None = None
    user_id: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def parse(cls, payload: dict[str, Any]) -> "Update":
        upd = cls(update_id=payload["update_id"], raw=payload)
        msg = payload.get("message") or payload.get("channel_post")
        cb = payload.get("callback_query")
        if cb:
            upd.callback_id = cb.get("id")
            upd.callback_data = cb.get("data")
            upd.user_id = (cb.get("from") or {}).get("id")
            msg = cb.get("message") or msg
        if msg:
            upd.chat_id = (msg.get("chat") or {}).get("id")
            upd.user_id = upd.user_id or (msg.get("from") or {}).get("id")
            upd.message_id = msg.get("message_id")
            upd.text = msg.get("text") or msg.get("caption")
            photos = msg.get("photo") or []
            if photos:
                # Telegram sends every rendered size; the last is the largest.
                upd.photo_file_id = photos[-1]["file_id"]
            doc = msg.get("document") or {}
            if not upd.photo_file_id and str(doc.get("mime_type", "")).startswith("image/"):
                upd.photo_file_id = doc["file_id"]
        return upd


class TelegramClient:
    """Thin wrapper over the Bot API.

    With no token the client runs in dry-run: calls are logged and return a
    stub response, so the whole pipeline can be exercised offline.
    """

    def __init__(self, token: str | None = None, timeout: int = 60):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN") or ""
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.token)

    # --- transport -------------------------------------------------------

    def _call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        params = {k: v for k, v in (params or {}).items() if v is not None}
        for key, value in list(params.items()):
            if isinstance(value, (dict, list)):
                params[key] = json.dumps(value)
        if not self.configured:
            log.info("DRY-RUN telegram.%s %s", method, params)
            return {"message_id": 0, "dry_run": True}
        url = f"{API_ROOT}/bot{self.token}/{method}"
        body = urllib.parse.urlencode(params).encode()
        return self._request(urllib.request.Request(url, data=body))

    def _call_multipart(
        self, method: str, params: dict[str, Any], file_field: str, path: str
    ) -> Any:
        if not self.configured:
            log.info("DRY-RUN telegram.%s %s file=%s", method, params, path)
            return {"message_id": 0, "dry_run": True}
        boundary = uuid.uuid4().hex
        chunks: list[bytes] = []
        for key, value in params.items():
            if value is None:
                continue
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            chunks.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n'
                f"{value}\r\n".encode()
            )
        name = os.path.basename(path)
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        with open(path, "rb") as fh:
            blob = fh.read()
        chunks.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
            f'filename="{name}"\r\nContent-Type: {ctype}\r\n\r\n'.encode()
        )
        chunks.append(blob)
        chunks.append(f"\r\n--{boundary}--\r\n".encode())
        req = urllib.request.Request(
            f"{API_ROOT}/bot{self.token}/{method}",
            data=b"".join(chunks),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        return self._request(req)

    def _request(self, req: urllib.request.Request) -> Any:
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:  # surface Telegram's own reason
            detail = exc.read().decode(errors="replace")[:400]
            raise TelegramError(f"HTTP {exc.code}: {detail}") from exc
        except OSError as exc:
            raise TelegramError(str(exc)) from exc
        if not payload.get("ok"):
            raise TelegramError(payload.get("description", "unknown error"))
        return payload.get("result")

    # --- API surface -----------------------------------------------------

    def get_updates(self, offset: int | None = None, limit: int = 50,
                    poll_timeout: int = 0) -> list[Update]:
        """Fetch pending updates. ``poll_timeout=0`` returns immediately."""
        result = self._call(
            "getUpdates",
            {
                "offset": offset,
                "limit": limit,
                "timeout": poll_timeout,
                "allowed_updates": ["message", "callback_query"],
            },
        )
        if not isinstance(result, list):
            return []
        return [Update.parse(item) for item in result]

    def send_message(self, chat_id: int, text: str, buttons: dict | None = None) -> Any:
        return self._call(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "reply_markup": buttons,
            },
        )

    def send_photo(self, chat_id: int, path: str, caption: str = "",
                   buttons: dict | None = None) -> Any:
        return self._call_multipart(
            "sendPhoto",
            {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML",
             "reply_markup": buttons},
            "photo",
            path,
        )

    def send_video(self, chat_id: int, path: str, caption: str = "",
                   buttons: dict | None = None) -> Any:
        return self._call_multipart(
            "sendVideo",
            {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML",
             "supports_streaming": True, "reply_markup": buttons},
            "video",
            path,
        )

    def send_document(self, chat_id: int, path: str, caption: str = "") -> Any:
        """Send the clip as a file so the original bytes survive re-encoding."""
        return self._call_multipart(
            "sendDocument",
            {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
            "document",
            path,
        )

    def clear_keyboard(self, chat_id: int, message_id: int) -> Any:
        """Drop the inline keyboard from a message whose step is finished."""
        try:
            return self._call("editMessageReplyMarkup",
                              {"chat_id": chat_id, "message_id": message_id})
        except TelegramError as exc:
            # Cosmetic: the state gate is what actually enforces the flow.
            log.debug("could not clear keyboard on %s: %s", message_id, exc)
            return None

    def answer_callback(self, callback_id: str, text: str = "") -> Any:
        return self._call("answerCallbackQuery", {"callback_query_id": callback_id,
                                                  "text": text})

    def download_file(self, file_id: str, dest: str) -> str:
        """Resolve a ``file_id`` and save its bytes to ``dest``."""
        if not self.configured:
            raise TelegramError("cannot download without TELEGRAM_BOT_TOKEN")
        info = self._call("getFile", {"file_id": file_id})
        url = f"{API_ROOT}/file/bot{self.token}/{info['file_path']}"
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        with urllib.request.urlopen(url, timeout=self.timeout) as resp, open(dest, "wb") as fh:
            fh.write(resp.read())
        return dest
