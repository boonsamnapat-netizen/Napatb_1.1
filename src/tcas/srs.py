"""Spaced repetition — SM-2 แบบย่อ.

หลักการ: ทบทวนถี่ตอนแรก แล้วยืดระยะออกเรื่อย ๆ ถ้ายังจำได้
ถ้าลืม (ตอบผิด) ให้รีเซ็ตกลับมาทบทวนพรุ่งนี้ทันที

ระยะทบทวนมาจาก config (`study.review_intervals_days`, ค่าเริ่มต้น 1/3/7/16/35 วัน)
แล้วปรับด้วย ease factor รายหัวข้อ — หัวข้อที่ผิดบ่อย ease จะต่ำลง ทำให้ทบทวนถี่ขึ้น
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List

DEFAULT_INTERVALS = [1, 3, 7, 16, 35]
EASE_START = 2.5
EASE_MIN = 1.3
EASE_MAX = 3.0
EASE_STEP_UP = 0.05
EASE_STEP_DOWN = 0.20

# น้ำหนักของผลลัพธ์ล่าสุดในการอัปเดตค่าความแม่น (0-1)
MASTERY_ALPHA = 0.30


def next_interval(repetition: int, ease: float, intervals: List[int] | None = None) -> int:
    """จำนวนวันจนถึงการทบทวนครั้งถัดไป.

    repetition = จำนวนครั้งที่ทบทวนผ่านติดต่อกันมาแล้ว (0 = เพิ่งอ่านรอบแรก)
    """
    table = intervals or DEFAULT_INTERVALS
    base = table[min(repetition, len(table) - 1)]
    if repetition >= len(table):
        # เกินตารางแล้ว — ยืดต่อด้วย ease ทบไปเรื่อย ๆ
        base = int(round(table[-1] * (ease ** (repetition - len(table) + 1))))
    scaled = base * (ease / EASE_START)
    return max(1, int(round(scaled)))


def schedule(
    record: Dict[str, Any],
    correct: bool,
    on: date,
    intervals: List[int] | None = None,
) -> Dict[str, Any]:
    """อัปเดตเรกคอร์ดหนึ่งรายการ (หัวข้อหรือข้อสอบ) หลังทบทวน/ตอบ.

    คืน dict ฟิลด์ที่เปลี่ยน — ผู้เรียกเอาไป merge ลง store เอง
    """
    ease = float(record.get("ease", EASE_START))
    repetition = int(record.get("repetition", 0))

    if correct:
        ease = min(EASE_MAX, ease + EASE_STEP_UP)
        repetition += 1
        gap = next_interval(repetition, ease, intervals)
    else:
        ease = max(EASE_MIN, ease - EASE_STEP_DOWN)
        repetition = 0
        gap = 1

    return {
        "ease": round(ease, 3),
        "repetition": repetition,
        "last_review": on.isoformat(),
        "next_review": (on + timedelta(days=gap)).isoformat(),
    }


def first_schedule(on: date, intervals: List[int] | None = None) -> Dict[str, Any]:
    """ตั้งคิวทบทวนครั้งแรกทันทีที่อ่านหัวข้อจบ."""
    table = intervals or DEFAULT_INTERVALS
    return {
        "learned_on": on.isoformat(),
        "ease": EASE_START,
        "repetition": 0,
        "next_review": (on + timedelta(days=table[0])).isoformat(),
    }


def update_mastery(current: float, correct: bool, alpha: float = MASTERY_ALPHA) -> float:
    """ค่าความแม่น 0-100 แบบ EWMA — ตอบถูกดันขึ้น ตอบผิดดึงลง."""
    target = 100.0 if correct else 0.0
    return round(current * (1 - alpha) + target * alpha, 1)
