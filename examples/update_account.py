#!/usr/bin/env python3
"""
Sync the live portfolio value from Telegram.

Send your bot a message like:  /port 150   (or "พอร์ต 150", or just "150")
This reads the latest such message via getUpdates and writes it to
data/account.json, which the scanner uses for position sizing.

If no portfolio message is found, the existing data/account.json is kept.
Requires env TELEGRAM_BOT_TOKEN.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
from datetime import datetime, timezone
from urllib.request import urlopen

ACCOUNT_FILE = pathlib.Path("data/account.json")
# "/port 150", "port 150", "พอร์ต 150", "account 150", "balance 150", or just "150"
_KEYWORD = re.compile(r"(?:/?port|พอร์ต|account|balance)\s*[:=]?\s*\$?\s*([\d][\d,\.]*)", re.I)
_BARE = re.compile(r"^\s*\$?\s*([\d][\d,\.]*)\s*$")


def _to_float(s: str) -> float | None:
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _extract(text: str) -> float | None:
    m = _KEYWORD.search(text or "")
    if m:
        return _to_float(m.group(1))
    m = _BARE.match(text or "")
    if m:
        v = _to_float(m.group(1))
        # ignore tiny bare numbers that are unlikely to be a balance
        return v if (v is not None and v >= 5) else None
    return None


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("No TELEGRAM_BOT_TOKEN — skipping account sync.")
        return 0
    try:
        with urlopen(f"https://api.telegram.org/bot{token}/getUpdates", timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"getUpdates failed: {e}")
        return 0

    latest_val, latest_ts = None, -1
    for upd in data.get("result", []):
        msg = upd.get("message") or upd.get("edited_message") or {}
        val = _extract(msg.get("text", ""))
        if val is not None and msg.get("date", 0) >= latest_ts:
            latest_val, latest_ts = val, msg.get("date", 0)

    if latest_val is None:
        if ACCOUNT_FILE.exists():
            print(f"No new portfolio message; keeping {ACCOUNT_FILE.read_text().strip()}")
        else:
            print("No portfolio message found and no existing account file.")
        return 0

    ACCOUNT_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACCOUNT_FILE.write_text(json.dumps({
        "account": latest_val,
        "updated": datetime.now(timezone.utc).isoformat(),
        "source": "telegram",
    }, indent=2))
    print(f"Updated portfolio value: ${latest_val:g}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
