"""Parse operator LINE messages into structured production records.

A typical message (Thai mixed with English) looks like::

    @NapatB. Manual # (1) Underfill  Runได้ปกติค่ะ Jun 17 2026  Day
    ✅️Run  95 Unit  ✅ไม่มี Fail L1  ✅ไม่มี Fail L2  ✅ไม่มี splash

The parser is deliberately tolerant: operators type by hand, so spacing,
emoji and ordering wobble. We anchor on stable keywords (machine number,
``Unit``, ``Fail L1/L2``, ``splash`` and a date) and pull the value that
sits next to each keyword.

Yield is **Pass / Total** where ``Pass = Total - (Fail L1 + Fail L2 + splash)``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

# ---------------------------------------------------------------------------
# Date handling
# ---------------------------------------------------------------------------

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# e.g. "Jun 17 2026"  or "17 Jun 2026"  or "2026-06-17"
_DATE_MONTH_FIRST = re.compile(
    r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})\s*,?\s+(\d{4})\b"
)
_DATE_DAY_FIRST = re.compile(
    r"\b(\d{1,2})\s+([A-Za-z]{3,9})\.?\s+(\d{4})\b"
)
_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def _find_date(text: str) -> tuple[date | None, int, int]:
    """Return (date, start, end) for the first date found, else (None, -1, -1)."""
    m = _DATE_ISO.search(text)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))), m.start(), m.end()
    m = _DATE_MONTH_FIRST.search(text)
    if m:
        mon = _MONTHS.get(m.group(1)[:3].lower())
        if mon:
            return date(int(m.group(3)), mon, int(m.group(2))), m.start(), m.end()
    m = _DATE_DAY_FIRST.search(text)
    if m:
        mon = _MONTHS.get(m.group(2)[:3].lower())
        if mon:
            return date(int(m.group(3)), mon, int(m.group(1))), m.start(), m.end()
    return None, -1, -1


# ---------------------------------------------------------------------------
# Field extraction helpers
# ---------------------------------------------------------------------------

_MACHINE = re.compile(r"#\s*\(?\s*(\d+)\s*\)?")
_MODE = re.compile(r"\b(manual|auto|automatic)\b", re.IGNORECASE)
_SHIFT = re.compile(r"\b(day|night|ด\s*ดึก|กลางวัน|กลางคืน)\b", re.IGNORECASE)
_QTY = re.compile(r"(\d+)\s*(?:unit|units|ชิ้น|pcs)\b", re.IGNORECASE)
_MACHINE_END = re.compile(r"#\s*\(?\s*\d+\s*\)?")


def _count_for(label_pattern: str, text: str) -> int:
    """Return the failure count that sits immediately before ``label``.

    The value must be *adjacent* to the label (only spaces between), so the
    ``ไม่มี`` of one label can't bleed into the next. ``ไม่มี`` (none) -> 0,
    an explicit number -> that number.
    """
    m = re.search(r"(ไม่มี|\d+)\s*" + label_pattern, text, re.IGNORECASE)
    if not m:
        return 0
    val = m.group(1)
    return 0 if val == "ไม่มี" else int(val)


@dataclass
class Record:
    """One parsed production report."""

    work_date: date | None
    machine: int | None
    mode: str
    issue_type: str
    shift: str
    total: int
    fail_l1: int
    fail_l2: int
    splash: int
    status_note: str
    raw: str
    warnings: list[str] = field(default_factory=list)

    @property
    def fails(self) -> int:
        return self.fail_l1 + self.fail_l2 + self.splash

    @property
    def passed(self) -> int:
        return self.total - self.fails

    @property
    def yield_ratio(self) -> float | None:
        if not self.total:
            return None
        return self.passed / self.total


def parse_message(text: str) -> Record:
    """Parse a single LINE message into a :class:`Record`."""

    raw = text.strip()
    warnings: list[str] = []

    machine = None
    m = _MACHINE.search(raw)
    if m:
        machine = int(m.group(1))
    else:
        warnings.append("ไม่พบหมายเลขเครื่อง (machine #)")

    mode = ""
    m = _MODE.search(raw)
    if m:
        mode = m.group(1).capitalize()
        if mode.lower() == "automatic":
            mode = "Auto"

    shift = ""
    m = _SHIFT.search(raw)
    if m:
        s = m.group(1).lower()
        shift = "Day" if s in {"day", "กลางวัน"} else "Night"

    work_date, date_start, _ = _find_date(raw)
    if work_date is None:
        warnings.append("ไม่พบวันที่ (date)")

    total = 0
    m = _QTY.search(raw)
    if m:
        total = int(m.group(1))
    else:
        warnings.append("ไม่พบจำนวนผลิต (Unit/total)")

    fail_l1 = _count_for(r"Fail\s*L\s*1", raw)
    fail_l2 = _count_for(r"Fail\s*L\s*2", raw)
    splash = _count_for(r"splash", raw)

    # The segment between the machine number and the date holds the issue
    # type (a leading English word) followed by a free-text status note.
    issue_type = ""
    status_note = ""
    mend = _MACHINE_END.search(raw)
    seg_start = mend.end() if mend else 0
    seg_end = date_start if date_start >= 0 else len(raw)
    if seg_end > seg_start:
        segment = raw[seg_start:seg_end].strip()
        im = re.match(r"([A-Za-z][A-Za-z /]*?)(?:\s{2,}|\s(?=[฀-๿]))", segment)
        if im:
            issue_type = im.group(1).strip()
            status_note = segment[im.end():].strip()
        else:
            status_note = segment

    rec = Record(
        work_date=work_date,
        machine=machine,
        mode=mode,
        issue_type=issue_type,
        shift=shift,
        total=total,
        fail_l1=fail_l1,
        fail_l2=fail_l2,
        splash=splash,
        status_note=status_note,
        raw=raw,
        warnings=warnings,
    )
    if rec.passed < 0:
        rec.warnings.append("ผลรวม Fail มากกว่าจำนวนผลิต — ตรวจสอบตัวเลข")
    return rec


def parse_messages(text: str) -> list[Record]:
    """Parse a blob of messages.

    Messages are separated by blank lines, or by a new ``@`` mention at the
    start of a line (the LINE bot prefixes each report with a mention).
    """
    blocks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.strip() == "":
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        if line.lstrip().startswith("@") and current:
            blocks.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current))

    return [parse_message(b) for b in blocks if b.strip()]
