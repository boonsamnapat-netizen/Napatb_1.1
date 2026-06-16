"""
Economic / crypto event calendar.

The headline scanner in news.py can only *guess* that something big is happening
from wording. This module knows the actual scheduled times of high-impact events
(FOMC, CPI, NFP, token unlocks, major listings…) so the engine can enforce a
precise blackout window: stand aside / size down for N hours before and after.

Events are loaded from a local YAML/JSON file (config.signal.calendar.file).
Keep it updated manually, or point `remote_url` at a JSON feed of the same shape.

Event schema (list of dicts):
  - time:     ISO-8601 timestamp, e.g. "2026-06-18T18:00:00Z"
  - name:     "FOMC rate decision"
  - impact:   "high" | "medium" | "low"
  - currency: "USD" | "BTC" | ... (optional)
  - assets:   ["BTC", "ETH"]  (optional; empty = affects whole market)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class CalendarEvent:
    time: datetime
    name: str
    impact: str = "high"
    currency: str = ""
    assets: list[str] = field(default_factory=list)

    def affects(self, base_asset: str) -> bool:
        if not self.assets:
            return True  # macro / market-wide
        return base_asset.upper() in {a.upper() for a in self.assets}

    def to_dict(self) -> dict:
        return {
            "time": self.time.isoformat(),
            "name": self.name,
            "impact": self.impact,
            "currency": self.currency,
            "assets": self.assets,
        }


def _parse_time(raw: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        return None


class EconomicCalendar:
    def __init__(self, config: dict):
        cfg = config.get("signal", {}).get("calendar", {})
        self.enabled = cfg.get("enabled", True)
        self.file = cfg.get("file", "config/economic_calendar.yaml")
        self.remote_url = cfg.get("remote_url", "")
        self.before_hours = float(cfg.get("blackout_before_hours", 4))
        self.after_hours = float(cfg.get("blackout_after_hours", 2))
        self.high_only = cfg.get("high_impact_only", True)
        self._events: list[CalendarEvent] | None = None

    # ---- loading --------------------------------------------------------
    def _load_events(self) -> list[CalendarEvent]:
        if self._events is not None:
            return self._events

        raw_events: list[dict] = []

        path = Path(self.file)
        if path.exists():
            try:
                if path.suffix in (".yaml", ".yml"):
                    import yaml

                    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                else:
                    data = json.loads(path.read_text(encoding="utf-8"))
                raw_events = data.get("events", data if isinstance(data, list) else [])
            except Exception as e:  # noqa: BLE001
                logger.warning("Failed to load calendar %s: %s", path, e)

        if self.remote_url:
            raw_events += self._fetch_remote()

        events: list[CalendarEvent] = []
        for ev in raw_events:
            t = _parse_time(ev.get("time", ""))
            if t is None:
                continue
            events.append(
                CalendarEvent(
                    time=t,
                    name=ev.get("name", "event"),
                    impact=str(ev.get("impact", "high")).lower(),
                    currency=ev.get("currency", ""),
                    assets=ev.get("assets", []) or [],
                )
            )
        events.sort(key=lambda e: e.time)
        self._events = events
        return events

    def _fetch_remote(self) -> list[dict]:
        try:
            import urllib.request

            with urllib.request.urlopen(self.remote_url, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data.get("events", data if isinstance(data, list) else [])
        except Exception as e:  # noqa: BLE001
            logger.info("Remote calendar fetch skipped: %s", e)
            return []

    # ---- queries --------------------------------------------------------
    def blackout(
        self, asset: str, now: datetime | None = None
    ) -> tuple[bool, list[CalendarEvent]]:
        """
        Are we inside the danger window of a relevant high-impact event?
        Returns (in_blackout, [events in window]).
        """
        if not self.enabled:
            return False, []
        now = now or datetime.now(timezone.utc)
        base = asset.upper().replace("/USDT", "").replace("USDT", "")

        hits: list[CalendarEvent] = []
        for ev in self._load_events():
            if self.high_only and ev.impact != "high":
                continue
            if not ev.affects(base):
                continue
            start = ev.time - timedelta(hours=self.before_hours)
            end = ev.time + timedelta(hours=self.after_hours)
            if start <= now <= end:
                hits.append(ev)
        return (len(hits) > 0), hits

    def upcoming(
        self, asset: str, within_hours: float = 24, now: datetime | None = None
    ) -> list[CalendarEvent]:
        now = now or datetime.now(timezone.utc)
        base = asset.upper().replace("/USDT", "").replace("USDT", "")
        horizon = now + timedelta(hours=within_hours)
        out = []
        for ev in self._load_events():
            if self.high_only and ev.impact != "high":
                continue
            if not ev.affects(base):
                continue
            if now <= ev.time <= horizon:
                out.append(ev)
        return out
