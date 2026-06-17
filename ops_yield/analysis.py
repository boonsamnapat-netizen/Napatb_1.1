"""Aggregations over parsed production records.

Pure functions that take an iterable of "fact" tuples and return summaries —
kept separate from Excel so they're easy to test. A fact is::

    (shift, total, passed, sender, notes)

Yields are combined the right way: sum pass / sum total, never averaging %.
"""

from __future__ import annotations

from collections import Counter, defaultdict

# Cause taxonomy learned from the real export. Order matters: a report is
# counted once per category if ANY of its synonyms appears in the notes.
CAUSE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("OT / สลับเบรค", ["OT", "สลับเบรค", "สลับเบรก", "สลับรัน", "สลับ"]),
    ("กาวไหลช้า", ["กาวไหลช้า", "กาวไหล", "กาวช้า"]),
    ("ซ่อม / ทำเครื่อง", ["ทำเครื่อง", "ซ่อม", "เครื่องเสีย", "เสีย", "Tech", "เทค",
                          "SHUTTLE", "ค้าง", "Down", "vendor", "เวนเดอร์", "หยุด"]),
    ("เทรนงาน", ["เทรน", "น้องใหม่", "สอนงาน"]),
    ("หัวกาว / เติมกาว", ["หัวกาว", "เติมกาว", "เปลี่ยนกาว", "กาวหมด"]),
    ("ล้างเบย์ / แม่บ้าน", ["ล้างเบย์", "เบย์", "แม่บ้าน"]),
    ("UV", ["UV"]),
    ("Gap / ตำแหน่งงาน", ["Gap", "gap", "ไม่ตรงตำแหน่ง", "ตำแหน่ง", "align", "Pic", "PIC"]),
]


def classify_causes(notes: str) -> list[str]:
    """Return the cause categories mentioned in a note string."""
    if not notes:
        return []
    hits = []
    for cat, kws in CAUSE_KEYWORDS:
        if any(kw in notes for kw in kws):
            hits.append(cat)
    return hits


def _yield(p: int, t: int):
    return p / t if t else None


def by_key(facts, key_fn) -> dict:
    """Aggregate (reports, total, passed) keyed by ``key_fn(fact)``."""
    agg: dict = defaultdict(lambda: [0, 0, 0])  # reports, total, pass
    for f in facts:
        k = key_fn(f)
        if k in (None, ""):
            continue
        a = agg[k]
        a[0] += 1
        a[1] += f[1]
        a[2] += f[2]
    return agg


def by_shift(facts) -> dict:
    return by_key(facts, lambda f: f[0])


def by_operator(facts) -> dict:
    return by_key(facts, lambda f: f[3])


def cause_summary(facts) -> dict:
    """category -> [reports_mentioning, fail_units_in_those_reports]."""
    out: dict = defaultdict(lambda: [0, 0])
    for shift, total, passed, sender, notes in facts:
        fails = total - passed
        for cat in classify_causes(notes):
            out[cat][0] += 1
            out[cat][1] += fails
    return out
