"""JSON-file persistence for bot jobs and the getUpdates offset.

A plain JSON file (not SQLite) so GitHub Actions can commit the state back to
the repo between scheduled runs and the diff stays readable.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

# Pipeline states, in the order a job moves through them.
CONFIRM_PRODUCT = "confirm_product"
CONFIRM_VIDEO = "confirm_video"
CHOOSE_LINK = "choose_link"
FINAL_CONFIRM = "final_confirm"
DELIVERED = "delivered"
CANCELLED = "cancelled"
FAILED = "failed"

TERMINAL = {DELIVERED, CANCELLED, FAILED}


@dataclass
class Job:
    """One product photo working its way to a finished clip."""

    id: str
    chat_id: int
    state: str
    created_at: float
    updated_at: float
    photo_path: str | None = None
    query: str | None = None
    candidates: list[dict[str, Any]] = field(default_factory=list)
    chosen: dict[str, Any] | None = None
    strategy: str | None = None
    video_path: str | None = None
    script: dict[str, Any] | None = None
    error: str | None = None

    def touch(self) -> None:
        self.updated_at = time.time()


class JobStore:
    """Load/save all jobs plus the update offset in a single JSON file."""

    def __init__(self, path: str = "data/affiliate_state.json"):
        self.path = path
        self._data: dict[str, Any] = {"offset": 0, "jobs": {}}
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as fh:
                loaded = json.load(fh)
        except (json.JSONDecodeError, OSError):
            # A truncated state file must not wedge the bot forever.
            return
        if isinstance(loaded, dict):
            self._data = {"offset": int(loaded.get("offset", 0)),
                          "jobs": loaded.get("jobs", {}) or {}}

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        # Write-then-rename: a killed Actions runner never leaves half a file.
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path) or ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(tmp, self.path)
        except BaseException:
            os.path.exists(tmp) and os.unlink(tmp)
            raise

    # --- offset ----------------------------------------------------------

    @property
    def offset(self) -> int:
        return int(self._data.get("offset", 0))

    @offset.setter
    def offset(self, value: int) -> None:
        self._data["offset"] = int(value)

    # --- jobs ------------------------------------------------------------

    def create(self, chat_id: int, state: str, **fields: Any) -> Job:
        now = time.time()
        job = Job(id=uuid.uuid4().hex[:8], chat_id=chat_id, state=state,
                  created_at=now, updated_at=now, **fields)
        self.put(job)
        return job

    def get(self, job_id: str) -> Job | None:
        raw = self._data["jobs"].get(job_id)
        return Job(**raw) if raw else None

    def put(self, job: Job) -> None:
        job.touch()
        self._data["jobs"][job.id] = asdict(job)

    def all(self) -> list[Job]:
        return [Job(**raw) for raw in self._data["jobs"].values()]

    def active_for_chat(self, chat_id: int) -> Job | None:
        """Most recent unfinished job for a chat, so replies need no job id."""
        live = [j for j in self.all() if j.chat_id == chat_id and j.state not in TERMINAL]
        return max(live, key=lambda j: j.updated_at) if live else None

    def prune(self, keep_seconds: float = 7 * 24 * 3600) -> int:
        """Drop finished jobs older than ``keep_seconds``. Returns count removed."""
        cutoff = time.time() - keep_seconds
        stale = [j.id for j in self.all() if j.state in TERMINAL and j.updated_at < cutoff]
        for job_id in stale:
            self._data["jobs"].pop(job_id, None)
        return len(stale)
