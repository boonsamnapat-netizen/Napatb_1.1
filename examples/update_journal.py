#!/usr/bin/env python3
"""
Maintain a trade journal from Telegram messages.

Message your bot to log trades (Thai or English, symbol can omit USDT):

  Open a trade:
    /trade AVAX short 6.19 6.804 5.50      ->  SYMBOL DIR ENTRY STOP [TP]
    /trade BTCUSDT long 65000 63200
    เปิด AVAX short 6.19 6.804

  Close a trade (R is computed from the stored entry/stop):
    /close AVAX 6.40                       ->  close latest open AVAX at price 6.40
    ปิด AVAX 6.40

This reads new messages via getUpdates and appends/updates
data/trade_journal.json (committed by the workflow). Each Telegram update is
processed once (tracked by update_id) so the same message is never logged twice.
A short confirmation is sent back to the chat for every logged action.

Requires env TELEGRAM_BOT_TOKEN (and TELEGRAM_CHAT_ID for confirmations).
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import urlopen

JOURNAL_FILE = pathlib.Path("data/trade_journal.json")

# Command verbs (slash or Thai word) so we don't collide with /port etc.
_OPEN = r"(?:/?trade|/?open|เปิด)"
_CLOSE = r"(?:/?close|/?exit|ปิด)"
_LONG = {"long", "buy", "ลอง", "ซื้อ", "l"}
_SHORT = {"short", "sell", "ช็อต", "ชอร์ต", "ขาย", "s"}

_OPEN_RE = re.compile(
    rf"^\s*{_OPEN}\s+([A-Za-z]{{2,15}})\s+(\w+|ลอง|ช็อต|ชอร์ต|ซื้อ|ขาย)\s+"
    r"([\d.,]+)\s+([\d.,]+)(?:\s+([\d.,]+))?",
    re.I,
)
_CLOSE_RE = re.compile(rf"^\s*{_CLOSE}\s+([A-Za-z]{{2,15}})\s+([\d.,]+)", re.I)
_STATS_RE = re.compile(r"^\s*(?:/?journal|/?stats|สถิติ|จดบันทึก)\s*$", re.I)


def _summary(journal: dict) -> str:
    trades = journal.get("trades", [])
    closed = [t for t in trades if t["status"] == "closed" and t["result_r"] is not None]
    open_t = [t for t in trades if t["status"] == "open"]
    lines = ["📓 Trade Journal"]
    if closed:
        wins = [t for t in closed if t["result_r"] > 0]
        total_r = sum(t["result_r"] for t in closed)
        wr = len(wins) / len(closed) * 100
        avg = total_r / len(closed)
        lines += [
            f"ปิดแล้ว {len(closed)} ไม้ | ชนะ {len(wins)} ({wr:.0f}%)",
            f"รวม {total_r:+.2f}R | เฉลี่ย {avg:+.3f}R/ไม้",
        ]
    else:
        lines.append("ยังไม่มีไม้ที่ปิด")
    if open_t:
        lines.append("กำลังถือ: " + ", ".join(
            f"{t['symbol']} {t['direction']}" for t in open_t))
    return "\n".join(lines)


def _f(s: str) -> float | None:
    try:
        return float(str(s).replace(",", ""))
    except (ValueError, AttributeError):
        return None


def _symbol(raw: str) -> str:
    s = raw.upper().replace("-USD", "USDT").replace("/", "")
    if not s.endswith("USDT"):
        s += "USDT"
    return s


def _dir(raw: str) -> str | None:
    w = raw.lower()
    if w in _LONG:
        return "LONG"
    if w in _SHORT:
        return "SHORT"
    return None


def _result_r(direction: str, entry: float, stop: float, exit_px: float) -> float | None:
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    move = (exit_px - entry) if direction == "LONG" else (entry - exit_px)
    return round(move / risk, 3)


def _load() -> dict:
    if JOURNAL_FILE.exists():
        try:
            return json.loads(JOURNAL_FILE.read_text())
        except Exception:  # noqa: BLE001
            pass
    return {"trades": [], "seen_update_ids": []}


def _send(token: str, text: str) -> None:
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not (token and chat):
        return
    try:
        q = urlencode({"chat_id": chat, "text": text})
        urlopen(f"https://api.telegram.org/bot{token}/sendMessage?{q}", timeout=10).read()
    except Exception:  # noqa: BLE001
        pass


def _apply(text: str, when: str, journal: dict) -> str | None:
    """Parse one message; mutate journal; return a confirmation string or None."""
    m = _OPEN_RE.match(text or "")
    if m:
        sym, draw, entry, stop, tp = m.groups()
        direction = _dir(draw)
        e, s = _f(entry), _f(stop)
        if direction is None or e is None or s is None:
            return None
        trade = {
            "symbol": _symbol(sym), "direction": direction,
            "entry": e, "stop": s, "tp": _f(tp) if tp else None,
            "status": "open", "opened": when,
            "exit": None, "result_r": None, "closed": None,
        }
        journal["trades"].append(trade)
        risk_pct = abs(e - s) / e * 100 if e else 0
        tp_txt = f" TP {trade['tp']:g}" if trade["tp"] else ""
        return (f"📓 บันทึกไม้ #{len(journal['trades'])}: {trade['symbol']} "
                f"{direction}\nEntry {e:g} | SL {s:g} ({risk_pct:.1f}%){tp_txt}")

    m = _CLOSE_RE.match(text or "")
    if m:
        sym, exit_raw = _symbol(m.group(1)), _f(m.group(2))
        if exit_raw is None:
            return None
        # close the most recent still-open trade for that symbol
        for tr in reversed(journal["trades"]):
            if tr["symbol"] == sym and tr["status"] == "open":
                r = _result_r(tr["direction"], tr["entry"], tr["stop"], exit_raw)
                tr.update(status="closed", exit=exit_raw, result_r=r, closed=when)
                tag = "✅ กำไร" if (r or 0) > 0 else ("➖ เสมอ" if r == 0 else "❌ ขาดทุน")
                return (f"{tag} ปิดไม้ {sym} {tr['direction']} @ {exit_raw:g}\n"
                        f"ผล: {r:+g}R" if r is not None else f"ปิดไม้ {sym} @ {exit_raw:g}")
        return f"⚠️ ไม่พบไม้ {sym} ที่เปิดอยู่"

    if _STATS_RE.match(text or ""):
        return _summary(journal)
    return None


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("No TELEGRAM_BOT_TOKEN — skipping journal sync.")
        return 0
    try:
        with urlopen(f"https://api.telegram.org/bot{token}/getUpdates", timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"getUpdates failed: {e}")
        return 0

    journal = _load()
    seen = set(journal.get("seen_update_ids", []))
    actions = 0
    # process in chronological order so opens precede their closes
    for upd in sorted(data.get("result", []), key=lambda u: u.get("update_id", 0)):
        uid = upd.get("update_id")
        if uid in seen:
            continue
        msg = upd.get("message") or upd.get("edited_message") or {}
        text = msg.get("text", "")
        when = datetime.fromtimestamp(
            msg.get("date", 0), tz=timezone.utc).isoformat() if msg.get("date") else ""
        confirm = _apply(text, when, journal)
        if confirm is not None:
            seen.add(uid)
            actions += 1
            print(confirm.replace("\n", " "))
            _send(token, confirm)

    # remember every update we have seen so re-runs never double-log
    for upd in data.get("result", []):
        seen.add(upd.get("update_id"))
    journal["seen_update_ids"] = sorted(i for i in seen if i is not None)[-500:]

    if actions:
        JOURNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        JOURNAL_FILE.write_text(json.dumps(journal, indent=2, ensure_ascii=False))
        n_open = sum(t["status"] == "open" for t in journal["trades"])
        print(f"Journal updated: {actions} action(s); {n_open} open / "
              f"{len(journal['trades'])} total.")
    else:
        print("No new journal commands.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
