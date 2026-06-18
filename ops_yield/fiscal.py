"""Fiscal calendar for the yield dashboards.

Work weeks run **Saturday → Friday**. The fiscal year is anchored so that
**Q1 FY27 starts Saturday 2026-07-04** (the team's chosen start; 5 Jul is a
Sunday so we snap to the Saturday that opens that work week). From there the
year is a clean 4 × 13-week grid (52 weeks), which is what the weekly/monthly/
quarterly tabs aggregate on. Months stay on the **calendar month** so a "month"
matches what people read off a date.

Each helper returns ``(sort_key, label)``: ``sort_key`` is the period's start
``date`` so the sheet sorts chronologically (label strings like "Q1 FY28" must
NOT be sorted alphabetically), and ``label`` is what the user sees.
"""

from __future__ import annotations

from datetime import date, timedelta

# Saturday that opens Q1 FY27.
FY_ANCHOR = date(2026, 7, 4)
FY_ANCHOR_NUM = 27

_QUARTER_WEEKS = 13
_YEAR_WEEKS = 52


def week_start(d: date) -> date:
    """The Saturday that opens the Sat→Fri work week containing ``d``."""
    # Mon=0 .. Sat=5 .. Sun=6; days since the week's Saturday
    return d - timedelta(days=(d.weekday() - 5) % 7)


def _week_index(d: date) -> int:
    """Whole weeks from FY_ANCHOR to ``d``'s week (negative for earlier dates)."""
    return (week_start(d) - FY_ANCHOR).days // 7


def week(d: date) -> tuple[date, str]:
    ws = week_start(d)
    n = _week_index(d)
    fy = FY_ANCHOR_NUM + (n // _YEAR_WEEKS)
    ww = n - (n // _YEAR_WEEKS) * _YEAR_WEEKS + 1  # 1..52
    return ws, f"WW{ww:02d} FY{fy} ({ws.strftime('%d %b')})"


def quarter(d: date) -> tuple[date, str]:
    n = _week_index(d)
    qi = n // _QUARTER_WEEKS           # global quarter index from the anchor
    fy = FY_ANCHOR_NUM + (qi // 4)
    q = qi - (qi // 4) * 4 + 1         # 1..4 within the fiscal year
    qstart = FY_ANCHOR + timedelta(weeks=qi * _QUARTER_WEEKS)
    return qstart, f"Q{q} FY{fy}"


def month(d: date) -> tuple[date, str]:
    return date(d.year, d.month, 1), d.strftime("%Y-%m")


def day(d: date) -> tuple[date, str]:
    return d, d.isoformat()
