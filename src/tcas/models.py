"""Dataclasses ที่ใช้ร่วมกันทั้งระบบ TCAS70."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

# พยัญชนะไทยที่ใช้เป็นตัวเลือกข้อสอบ — เขียนเป็นลิสต์เพราะรหัส Unicode ไม่ต่อเนื่อง
CHOICE_LETTERS = ["ก", "ข", "ค", "ง", "จ"]


@dataclass(frozen=True)
class Topic:
    """หัวข้อย่อยหนึ่งหัวข้อในวิชาหนึ่ง."""

    code: str
    name: str
    # น้ำหนักการออกสอบ 1-5 (5 = ออกแทบทุกปี หลายข้อ)
    weight: int
    # ชั่วโมงที่ควรใช้อ่านรอบแรกจนเข้าใจ + ทำโจทย์
    hours: float

    @property
    def key(self) -> str:
        return self.code


@dataclass(frozen=True)
class Subject:
    """วิชาหนึ่งวิชา (A-Level หนึ่งรหัส หรือ TPAT1)."""

    code: str
    name: str
    # 'tpat1' หรือ 'alevel'
    exam: str
    # กลุ่มถ่วงน้ำหนักของ กสพท: science / math1 / english / thai / social / tpat1
    group: str
    max_score: float
    topics: List[Topic] = field(default_factory=list)

    @property
    def total_hours(self) -> float:
        return sum(t.hours for t in self.topics)


@dataclass
class StudyBlock:
    """บล็อกอ่านหนังสือหนึ่งช่วงในตาราง."""

    subject_code: str
    subject_name: str
    topic_code: str
    topic_name: str
    hours: float
    # 'learn' = อ่านรอบแรก, 'review' = ทบทวนตามคิว SRS
    kind: str
    # ครั้งที่ทบทวน (0 = อ่านรอบแรก)
    repetition: int = 0

    def label(self) -> str:
        tag = "อ่านใหม่" if self.kind == "learn" else f"ทบทวน #{self.repetition}"
        return f"{self.subject_name} · {self.topic_name} ({tag})"


@dataclass
class StudyDay:
    """หนึ่งวันในตารางอ่านหนังสือ."""

    day: date
    blocks: List[StudyBlock] = field(default_factory=list)
    note: str = ""

    @property
    def hours(self) -> float:
        return sum(b.hours for b in self.blocks)


@dataclass(frozen=True)
class Question:
    """ข้อสอบหนึ่งข้อในคลัง."""

    qid: str
    subject_code: str
    topic_code: str
    stem: str
    choices: List[str]
    # index ของตัวเลือกที่ถูก (0-based)
    answer: int
    explanation: str = ""
    # 1 = ง่าย, 2 = กลาง, 3 = ยาก
    difficulty: int = 2
    source: str = ""

    def choice_label(self, index: int) -> str:
        """ป้ายตัวเลือกแบบไทย: ก ข ค ง จ (ไม่ใช้ chr() เพราะพยัญชนะไทยไม่เรียงติดกัน)."""
        return CHOICE_LETTERS[index] if index < len(CHOICE_LETTERS) else str(index + 1)

    def answer_label(self) -> str:
        return f"{self.choice_label(self.answer)}. {self.choices[self.answer]}"


@dataclass
class QuizResult:
    """ผลการทำชุดข้อสอบหนึ่งชุด."""

    subject_code: str
    total: int
    correct: int
    wrong_qids: List[str] = field(default_factory=list)
    per_topic: Dict[str, List[int]] = field(default_factory=dict)  # topic -> [correct, total]

    @property
    def pct(self) -> float:
        return 100.0 * self.correct / self.total if self.total else 0.0


@dataclass
class ScoreCard:
    """ผลการคำนวณคะแนนรวม กสพท."""

    total: float
    # กลุ่ม -> (คะแนนดิบ %, คะแนนถ่วงน้ำหนัก)
    breakdown: Dict[str, tuple]
    passed_minimums: bool
    failures: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)


@dataclass
class ProgramChance:
    """โอกาสติดของคณะหนึ่ง เทียบกับคะแนนที่คาดว่าจะได้."""

    code: str
    name: str
    faculty: str
    seats: Optional[int]
    latest_cutoff: Optional[float]
    trend: float          # คะแนนต่ำสุดขยับขึ้น/ลงเฉลี่ยต่อปี
    projected_cutoff: Optional[float]
    margin: Optional[float]   # คะแนนเรา - คะแนนต่ำสุดที่คาด
    band: str                 # ปลอดภัย / ลุ้น / ท้าทาย / เกินเอื้อม / ไม่มีข้อมูล
    verified: bool
