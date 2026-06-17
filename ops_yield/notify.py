"""End-of-day Telegram summary for the yield system.

Posts a short Thai recap of the latest production day to a Telegram chat
(reuses the crypto system's ``TELEGRAM_BOT_TOKEN`` / ``TELEGRAM_CHAT_ID``
secrets). Runs from GitHub Actions where the runner has internet; the sandbox
can't reach Telegram, so this is exercised only in CI.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections import defaultdict

from .parser import Record

_LOW_YIELD = 0.95  # flag a machine/day below this


def send_telegram(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    with urllib.request.urlopen(url, data=data, timeout=30) as resp:
        resp.read()


def build_daily_summary(records: list[Record], prior_actions: dict,
                        sheet_url: str | None = None) -> str:
    """Recap the most recent work date present in ``records``."""
    dates = [r.work_date for r in records if r.work_date]
    if not dates:
        return "📊 สรุป Yield: ไม่มีข้อมูลวันล่าสุด"
    latest = max(dates)
    day = [r for r in records if r.work_date == latest]

    tot = sum(r.total or 0 for r in day)
    passed = sum(r.passed or 0 for r in day)
    y = (passed / tot) if tot else None

    # per-machine yield for the day
    agg: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in day:
        agg[r.machine][0] += r.passed or 0
        agg[r.machine][1] += r.total or 0
    low = []
    for m, (p, t) in agg.items():
        if t and p / t < _LOW_YIELD:
            low.append((p / t, m))
    low.sort()

    fail_reports = sum(1 for r in day if r.fails > 0)
    fail_units = sum(r.fails for r in day)

    # all-time issues still open (not Done / Ignore)
    closed = sum(1 for _, st in prior_actions.values()
                 if (st or "").strip() in ("Done", "Ignore"))
    open_issues = max(len(prior_actions) - closed, 0)

    lines = [
        f"📊 <b>สรุป Yield วันที่ {latest.isoformat()}</b>",
        f"รายงาน: {len(day)} ใบ | เครื่อง {len(agg)} เครื่อง",
        f"Yield รวมวันนี้: <b>{y*100:.1f}%</b>" if y is not None else "Yield รวม: —",
        f"🔧 รายงานที่มี fail: {fail_reports} ใบ ({fail_units} units)",
    ]
    if low:
        worst = ", ".join(f"{m} ({r*100:.0f}%)" for r, m in low[:5])
        lines.append(f"⚠️ เครื่อง yield ต่ำ: {worst}")
    lines.append(f"📋 เหตุการณ์ค้างแก้ (ยังไม่ Done): {open_issues}")
    if sheet_url:
        lines.append(f'🔗 <a href="{sheet_url}">เปิด Google Sheet</a>')
    return "\n".join(lines)
