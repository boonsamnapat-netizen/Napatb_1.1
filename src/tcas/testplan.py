"""สร้าง 'ตารางทดสอบ' — ควรสอบวัดผลอะไร เมื่อไร.

อ่านหนังสืออย่างเดียวไม่พอ ต้องวัดผลเป็นระยะถึงจะรู้ว่าจำได้จริงไหม
โมดูลนี้สร้างตารางทดสอบ 3 ระดับจากตารางอ่านหนังสือ + วันสอบจริง

  1. quiz รายสัปดาห์  — ทุกสุดสัปดาห์ ทดสอบเฉพาะหัวข้อที่เพิ่งอ่านไปในสัปดาห์นั้น
                        (ทดสอบสิ่งที่เพิ่งเรียนคือวิธีที่ทำให้จำได้นานที่สุด)
  2. ทดสอบรวมรายเดือน — ทุกสิ้นเดือน ทดสอบทั้งวิชาที่อ่านสะสมมา ไม่ใช่แค่ของใหม่
  3. สอบเสมือนจริง    — นับถอยหลังจากวันสอบจริง จับเวลาเต็มรูปแบบ

เวลาที่ใช้สอบถูกหักออกจากตารางอ่านของวันนั้นโดยปริยาย — ตารางทดสอบเป็น
'สิ่งที่ต้องทำเพิ่ม' ในวันนั้น ไม่ได้ไปแก้ตารางอ่าน เพราะการสอบใช้เวลาไม่มาก
ยกเว้นวันสอบเสมือนจริงซึ่งกินเวลาครึ่งวัน
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from . import syllabus
from .config import exam_dates
from .models import StudyDay

# จำนวนวันก่อนสอบจริง ที่ควรลงสอบเสมือนจริง
MOCK_OFFSETS_DAYS = [60, 30, 14, 7]

# ระยะเวลาสอบจริงของแต่ละสนาม (ชั่วโมง) — ใช้บอกว่าต้องกันเวลาไว้เท่าไร
MOCK_DURATION_HOURS = {"tpat1": 3.0, "alevel": 3.0, "tgat_tpat": 3.0}

KIND_WEEKLY = "weekly"
KIND_MONTHLY = "monthly"
KIND_MOCK = "mock"

KIND_LABELS = {
    KIND_WEEKLY: "ทดสอบประจำสัปดาห์",
    KIND_MONTHLY: "ทดสอบรวมประจำเดือน",
    KIND_MOCK: "สอบเสมือนจริง",
}


@dataclass
class TestEvent:
    """การทดสอบหนึ่งครั้งในตาราง."""

    day: date
    kind: str
    title: str
    # วิชาที่ต้องทดสอบ
    subjects: List[str] = field(default_factory=list)
    # หัวข้อที่เน้น (เฉพาะ quiz รายสัปดาห์)
    topics: List[str] = field(default_factory=list)
    questions: int = 0
    minutes: int = 0
    note: str = ""

    @property
    def subject_names(self) -> List[str]:
        return [
            syllabus.SUBJECTS[c].name for c in self.subjects if c in syllabus.SUBJECTS
        ]


def _bank_counts(bank) -> Dict[str, int]:
    """นับข้อสอบต่อหัวข้อจากคลังจริง — คีย์คือรหัสหัวข้อ."""
    counts: Dict[str, int] = {}
    for q in (bank or {}).values():
        if q.topic_code:
            counts[q.topic_code] = counts.get(q.topic_code, 0) + 1
    return counts


def _available(counts: Dict[str, int], topics) -> int:
    return sum(counts.get(t, 0) for t in topics)


def _weekly_events(
    plan: List[StudyDay],
    counts: Optional[Dict[str, int]] = None,
    questions_per_topic: int = 2,
) -> List[TestEvent]:
    """รวมหัวข้อที่อ่านในแต่ละสัปดาห์ แล้วตั้งเป็นการทดสอบวันอาทิตย์ท้ายสัปดาห์.

    จำนวนข้อที่บอก ต้องไม่เกินที่คลังมีจริง — ไม่งั้นแอปสัญญาสิ่งที่ทำไม่ได้
    """
    # จัดกลุ่มตามสัปดาห์ ISO
    weeks: Dict[tuple, Dict[str, Any]] = {}
    for sd in plan:
        if not sd.blocks:
            continue
        key = sd.day.isocalendar()[:2]
        bucket = weeks.setdefault(key, {"topics": {}, "last": sd.day})
        bucket["last"] = max(bucket["last"], sd.day)
        for b in sd.blocks:
            if b.kind == "learn":
                bucket["topics"][b.topic_code] = b.subject_code

    events = []
    for _key, bucket in sorted(weeks.items()):
        topics = bucket["topics"]
        if not topics:
            continue
        subjects = sorted(set(topics.values()))
        # สอบวันอาทิตย์ของสัปดาห์นั้น (หรือวันสุดท้ายที่มีตาราง ถ้าเลยไปแล้ว)
        last = bucket["last"]
        sunday = last + timedelta(days=(6 - last.weekday()))

        want = len(topics) * questions_per_topic
        have = _available(counts, topics) if counts is not None else want
        n = min(want, have)

        note = "เน้นเฉพาะของใหม่ ทำทันทีที่จบสัปดาห์ตอนยังจำได้"
        if counts is not None and have < want:
            gap = [t for t in sorted(topics) if not counts.get(t)]
            if not n:
                note = (
                    f"⚠️ ยังไม่มีข้อสอบของ {len(gap)} หัวข้อนี้ในคลัง — "
                    "เพิ่มได้ที่ data/tcas/questions/ แล้วรัน export ใหม่"
                )
            elif gap:
                note += f" (คลังยังขาดข้อสอบ {len(gap)} หัวข้อ)"

        events.append(
            TestEvent(
                day=sunday,
                kind=KIND_WEEKLY,
                title=f"ทดสอบหัวข้อที่อ่านสัปดาห์นี้ ({len(topics)} หัวข้อ)",
                subjects=subjects,
                topics=sorted(topics),
                questions=n,
                minutes=max(10, n * 2) if n else 0,
                note=note,
            )
        )
    return events


def _monthly_events(
    plan: List[StudyDay], counts: Optional[Dict[str, int]] = None
) -> List[TestEvent]:
    """สิ้นเดือน ทดสอบรวมทุกวิชาที่อ่านสะสมมาถึงตอนนั้น."""
    months: Dict[tuple, Dict[str, Any]] = {}
    for sd in plan:
        if not sd.blocks:
            continue
        key = (sd.day.year, sd.day.month)
        bucket = months.setdefault(key, {"subjects": set(), "topics": set(), "last": sd.day})
        bucket["last"] = max(bucket["last"], sd.day)
        for b in sd.blocks:
            bucket["subjects"].add(b.subject_code)
            bucket["topics"].add(b.topic_code)

    events = []
    cumulative: set = set()
    cumulative_topics: set = set()
    for _key, bucket in sorted(months.items()):
        cumulative |= bucket["subjects"]
        cumulative_topics |= bucket["topics"]
        subjects = sorted(cumulative)

        want = len(subjects) * 10
        have = _available(counts, cumulative_topics) if counts is not None else want
        n = min(want, have)

        note = "รวมของเก่าทั้งหมด ไม่ใช่แค่เดือนนี้ — วัดว่าของเดิมยังอยู่ไหม"
        if counts is not None and have < want:
            note += f" (คลังมีข้อสอบให้ {n} ข้อ จากที่ควรได้ {want})"

        events.append(
            TestEvent(
                day=bucket["last"],
                kind=KIND_MONTHLY,
                title=f"ทดสอบรวมสะสม {len(subjects)} วิชา",
                subjects=subjects,
                topics=sorted(cumulative_topics),
                questions=n,
                minutes=max(10, n * 90 // 60) if n else 0,
                note=note,
            )
        )
    return events


def _mock_events(cfg: Dict[str, Any], start: date) -> List[TestEvent]:
    """สอบเสมือนจริง นับถอยหลังจากวันสอบจริงแต่ละสนาม."""
    exams = exam_dates(cfg)
    events = []
    for key, spec in exams.items():
        exam_day = spec["date"]
        # วิชาที่ต้องใช้ในสนามนั้น
        if key == "tpat1":
            subjects = [c for c, s in syllabus.SUBJECTS.items() if s.exam == "tpat1"]
        elif key == "alevel":
            subjects = [c for c, s in syllabus.SUBJECTS.items() if s.exam == "alevel"]
        else:
            continue  # TGAT/TPAT2-5 ไม่ได้ใช้ในเกณฑ์ กสพท จึงไม่ตั้งสอบเสมือน

        duration = MOCK_DURATION_HOURS.get(key, 3.0)
        real_exam_days = {s["date"] for s in exams.values()}

        for offset in MOCK_OFFSETS_DAYS:
            day = exam_day - timedelta(days=offset)
            # อย่าไปลงชนวันสอบจริงสนามอื่น — เลื่อนถอยหลังจนกว่าจะว่าง
            while day in real_exam_days:
                day -= timedelta(days=1)
            if day < start:
                continue

            note = "จับเวลาเต็มรูปแบบ ห้ามเปิดหนังสือ แล้วจดว่าพลาดเพราะอะไร"
            if key == "alevel":
                # A-Level สอบจริงกระจาย 2-3 วัน ซ้อมทั้ง 7 วิชารวดเดียวไม่สมจริง
                note += f" — แบ่งสอบ 2-3 วัน วันละ 2-3 วิชา (ทั้งหมด {len(subjects)} วิชา)"
            events.append(
                TestEvent(
                    day=day,
                    kind=KIND_MOCK,
                    title=f"สอบเสมือนจริง: {spec['name']} (ก่อนสอบ {offset} วัน)",
                    subjects=sorted(subjects),
                    questions=0,
                    minutes=int(duration * 60),
                    note=note,
                )
            )
    return events


def generate(
    cfg: Dict[str, Any],
    plan: List[StudyDay],
    start: Optional[date] = None,
    bank=None,
) -> List[TestEvent]:
    """สร้างตารางทดสอบทั้งหมด เรียงตามวัน.

    ส่ง `bank` (ผลจาก quiz.load_bank) มาด้วยเสมอถ้าทำได้ — จำนวนข้อที่แสดง
    จะได้ไม่เกินที่คลังมีจริง ถ้าไม่ส่งมาจะกลับไปใช้ค่าประมาณแบบเดิม
    """
    if not plan:
        return []
    start = start or plan[0].day
    counts = _bank_counts(bank) if bank is not None else None
    events = (
        _weekly_events(plan, counts)
        + _monthly_events(plan, counts)
        + _mock_events(cfg, start)
    )

    # ถ้าวันเดียวกันชนกัน ให้สอบเสมือนจริงมาก่อน แล้วรายเดือน แล้วรายสัปดาห์
    priority = {KIND_MOCK: 0, KIND_MONTHLY: 1, KIND_WEEKLY: 2}
    events.sort(key=lambda e: (e.day, priority.get(e.kind, 9)))
    return [e for e in events if e.day >= start]


def next_test(events: List[TestEvent], on: date) -> Optional[TestEvent]:
    for e in events:
        if e.day >= on:
            return e
    return None


def tests_on(events: List[TestEvent], day: date) -> List[TestEvent]:
    return [e for e in events if e.day == day]
