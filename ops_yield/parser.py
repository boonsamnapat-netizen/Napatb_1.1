"""Parse operator LINE messages into structured production records.

Learned from a real LINE export (group "Super Underfill", 2022-2026). The
*current* daily-report format (mid-2026) looks like::

    @NapatB. เครื่องAUTO Underfill #(5)
    Run ได้ปกติครับ
    Jun 17 2026 Day
    ✅Run 79 Unit
    ✅ไม่มี Fail L1
    ❌มี Fail L2  2 Unit
    ✅ไม่มี Splash

Real-world wobble this parser handles (all seen in the export):
  * machine number in ``#(5)`` / ``# (1)`` / ``(7)`` — or Thai text ``#(เคาท์ดาวน์)``
  * mode ``Manual`` or ``AUTO`` (often glued: ``เครื่องAUTO``)
  * a *fail count comes AFTER the label*: ``มี Fail L1  1 Unit`` -> 1
  * ``ไม่มี <label>`` -> 0 (none); the ✅/❌ emoji is NOT reliable
  * label spacing/gluing: ``Fail L 2``, ``ไม่มีFail L2``, ``ไม่มีSplash``
  * the ``(ไม่มีทาง)มี Fail L1 1 Unit`` trap — an explicit count wins over "ไม่มี"

Yield = Pass / Total, Pass = Total - (Fail L1 + Fail L2 + Splash).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

# ---------------------------------------------------------------------------
# Date handling
# ---------------------------------------------------------------------------

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_DATE_MONTH_FIRST = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})\s*,?\s+(\d{4})\b")
_DATE_DAY_FIRST = re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\.?\s+(\d{4})\b")
_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def _parse_date(text: str) -> date | None:
    m = _DATE_ISO.search(text)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _DATE_MONTH_FIRST.search(text)
    if m:
        mon = _MONTHS.get(m.group(1)[:3].lower())
        if mon:
            return date(int(m.group(3)), mon, int(m.group(2)))
    m = _DATE_DAY_FIRST.search(text)
    if m:
        mon = _MONTHS.get(m.group(2)[:3].lower())
        if mon:
            return date(int(m.group(3)), mon, int(m.group(1)))
    return None


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------

# machine id inside parentheses, preferring the one near '#'
_MACHINE_HASH = re.compile(r"#\s*\(\s*([^)\n]+?)\s*\)")
_MACHINE_UF = re.compile(r"(?:Underfill|เครื่อง)\D{0,6}\(\s*([^)\n]+?)\s*\)")
_MACHINE_NUM = re.compile(r"\(\s*(\d+)\s*\)")
_MACHINE_HASH_BARE = re.compile(r"#\s*(\d+)")
# number glued to / after the word Underfil(l), no '#': "Underfill3", "Underfil 4"
_MACHINE_AFTER_UF = re.compile(r"Underfil{1,2}\s*#?\s*(\d+)", re.IGNORECASE)
_PAREN = re.compile(r"\(\s*([^)\n]+?)\s*\)")
_NO_MORE = re.compile(r"ไม่\s*มี")  # "ไม่มี" / "ไม่ มี" -> none
# lines that are part of the report structure (skipped when collecting notes)
_STRUCT_LINE = re.compile(
    r"@NapatB|\bRun\b|Unit|Fail\s*L|plash|\bDay\b|\bNight\b|Manual|AUTO"
    r"|เครื่อง|Underfil|ปกติ|\d{4}", re.IGNORECASE)

_RUN_QTY = re.compile(r"Run\D{0,4}(\d+)\s*(?:Unit|unit|ชิ้น|ตัว)", re.IGNORECASE)
_ANY_QTY = re.compile(r"(\d+)\s*(?:Unit|unit|ชิ้น|ตัว)", re.IGNORECASE)
_SHIFT = re.compile(r"\b(day|night)\b|กลางวัน|กลางคืน|กะดึก|กะเช้า", re.IGNORECASE)
_NUM_UNIT = re.compile(r"(\d+)\s*(?:Unit|unit|ชิ้น|ตัว)?", re.IGNORECASE)

_LABELS = {
    "fail_l1": re.compile(r"Fail\s*L\s*1", re.IGNORECASE),
    "fail_l2": re.compile(r"Fail\s*L\s*2", re.IGNORECASE),
    "splash": re.compile(r"splash", re.IGNORECASE),
}


def _count_label(label_re: re.Pattern, text: str) -> tuple[int, str]:
    """Return ``(count, status)`` for a failure label.

    ``status`` is one of ``absent`` (label not in the message — operator didn't
    track it, treated as 0), ``none`` (``ไม่มี`` -> 0), ``count`` (explicit
    number) or ``ambiguous`` (``มี`` with no number — needs a human look).
    The count always sits AFTER the label in this group's format.
    """
    m = label_re.search(text)
    if not m:
        return 0, "absent"

    after = text[m.end():]
    cut = len(after)
    for other in _LABELS.values():
        om = other.search(after)
        if om:
            cut = min(cut, om.start())
    nl = after.find("\n")
    if nl >= 0:
        cut = min(cut, nl)
    after = after[:cut]

    num = _NUM_UNIT.search(after)
    if num:
        return int(num.group(1)), "count"

    before = text[max(0, m.start() - 14):m.start()]
    if _NO_MORE.search(before):
        return 0, "none"
    if "มี" in before:
        return 0, "ambiguous"
    return 0, "none"


@dataclass
class Record:
    """One parsed production report."""

    work_date: date | None
    machine: str
    mode: str
    issue_type: str
    shift: str
    total: int
    fail_l1: int
    fail_l2: int
    splash: int
    status_note: str
    raw: str
    sender: str = ""
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


def parse_message(text: str, *, sender: str = "") -> Record:
    """Parse a single LINE message into a :class:`Record`."""
    raw = text.strip()
    warnings: list[str] = []

    # --- machine -----------------------------------------------------------
    # The machine id lives in parentheses in the header (first non-empty line):
    # ``#(5)`` / ``# (1)`` / ``Manual(1)`` / ``Underfil (เคาท์ดาวน์)``.
    machine = ""
    first_line = next((l for l in raw.splitlines() if l.strip()), "")
    m = (_MACHINE_NUM.search(first_line) or _PAREN.search(first_line)
         or _MACHINE_HASH_BARE.search(first_line)
         or _MACHINE_AFTER_UF.search(first_line))
    if m:
        machine = m.group(1).strip()
    else:
        for pat in (_MACHINE_HASH, _MACHINE_HASH_BARE, _MACHINE_AFTER_UF,
                    _MACHINE_UF, _MACHINE_NUM):
            m = pat.search(raw)
            if m:
                machine = m.group(1).strip()
                break
    machine = machine.strip(" ()[].#-•·")
    if "เคาท์ดาวน์" in machine or "เคาน์ดาวน์" in machine:
        machine = "เคาท์ดาวน์"
    if not machine or machine.lower() in {"emoji", "sticker", "photo"}:
        machine = ""
        warnings.append("ไม่พบหมายเลขเครื่อง")

    # --- mode --------------------------------------------------------------
    low = raw.lower()
    mode = "Manual" if "manual" in low else ("Auto" if "auto" in low else "")

    # --- issue type --------------------------------------------------------
    issue_type = "Underfill" if "underfill" in low else ""

    # --- shift -------------------------------------------------------------
    shift = ""
    m = _SHIFT.search(raw)
    if m:
        token = (m.group(0) or "").lower()
        shift = "Night" if token in {"night", "กลางคืน", "กะดึก"} else "Day"

    # --- date --------------------------------------------------------------
    work_date = _parse_date(raw)
    if work_date is None:
        warnings.append("ไม่พบวันที่")

    # --- run quantity (total) ---------------------------------------------
    total = 0
    m = _RUN_QTY.search(raw)
    if m:
        total = int(m.group(1))
    else:
        m = _ANY_QTY.search(raw)
        if m:
            total = int(m.group(1))
        else:
            warnings.append("ไม่พบจำนวนผลิต (Run/Unit)")

    # --- failures ----------------------------------------------------------
    # Missing labels are treated as 0 (operators don't always report every
    # category); only an explicit "มี" with no number is worth flagging.
    fail_l1, s1 = _count_label(_LABELS["fail_l1"], raw)
    fail_l2, s2 = _count_label(_LABELS["fail_l2"], raw)
    splash, ss = _count_label(_LABELS["splash"], raw)
    for status, name in ((s1, "Fail L1"), (s2, "Fail L2"), (ss, "Splash")):
        if status == "ambiguous":
            warnings.append(f"{name}: เขียน 'มี' แต่ไม่ระบุจำนวน")

    # --- notes / cause lines ----------------------------------------------
    # Keep the free-text lines that aren't structural (header/date/run/fail) —
    # these carry the cause ("กาวไหลช้า", "OT สลับเบรค", "ซ่อมเครื่อง", ...).
    note_lines = []
    for line in raw.splitlines():
        if _STRUCT_LINE.search(line):
            continue
        cleaned = line.strip(" *#✅❌✓​️.()")
        if cleaned:
            note_lines.append(cleaned)
    status_note = "; ".join(note_lines)

    rec = Record(
        work_date=work_date, machine=machine, mode=mode, issue_type=issue_type,
        shift=shift, total=total, fail_l1=fail_l1, fail_l2=fail_l2,
        splash=splash, status_note=status_note, raw=raw, sender=sender,
        warnings=warnings,
    )
    if rec.passed < 0:
        rec.warnings.append("ผลรวม Fail มากกว่าจำนวนผลิต — ตรวจสอบตัวเลข")
    return rec


def looks_like_report(text: str) -> bool:
    """Heuristic: is this message a daily production report (current format)?"""
    low = text.lower()
    return ("fail l" in low or "splash" in low) and bool(_ANY_QTY.search(text))


def parse_messages(text: str) -> list[Record]:
    """Parse a blob of messages separated by blank lines or new ``@`` mentions."""
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
