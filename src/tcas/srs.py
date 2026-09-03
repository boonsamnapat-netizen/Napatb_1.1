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

def next_interval(repetition: int, ease: float, intervals: List[int] | None = None) -> int:
    """จำนวนวันจนถึงการทบทวนครั้งถัดไป — อ่านตรงจากตาราง ไม่คูณ ease.

    repetition = จำนวนครั้งที่ทบทวนผ่านติดต่อกันมาแล้ว (0 = เพิ่งอ่านรอบแรก)
    เลยท้ายตารางแล้วก็คงที่ที่ค่าสุดท้าย (ค่าเริ่มต้น 35 วัน)

    ⚠️ `ease` ยังรับไว้เพื่อความเข้ากันได้ของผู้เรียก และยังถูกเก็บลง store
    (ใช้ดูว่าหัวข้อไหนพลาดบ่อย) แต่ **ไม่มีผลต่อระยะทบทวน** โดยตั้งใจ:
    ฝั่งแอป (`tcas_app.html`) ไม่มีฟิลด์ ease เลย ใช้ตารางแบน ๆ ล้วน
    ถ้าฝั่งนี้คูณ ease ตารางทบทวนสองฝั่งจะแยกกันตั้งแต่ครั้งแรก
    (ease เริ่มที่ 2.5 บวกครั้งละ 0.05 ทบไปเรื่อย ๆ เกินตารางแล้วยิ่งบานปลาย)
    จะเอา ease กลับมาใช้เมื่อไหร่ ต้องใส่ในฝั่งแอปพร้อมกันเท่านั้น
    """
    table = intervals or DEFAULT_INTERVALS
    return max(1, int(table[min(repetition, len(table) - 1)]))


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

