"""เก็บความคืบหน้าลง JSON — หัวข้อที่อ่านแล้ว, คิวทบทวน, สถิติ quiz, คะแนน.

ไฟล์เดียวจบ (`data/tcas/progress.json`) เพื่อให้ commit ขึ้น git ได้และ
GitHub Actions หยิบไปใช้ต่อได้ทันที
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict

from .config import parse_date, resolve_path

SCHEMA_VERSION = 1


def _empty() -> Dict[str, Any]:
    return {
        "version": SCHEMA_VERSION,
        # topic_code -> {hours_done, learned_on, repetition, next_review, ease, mastery}
        "topics": {},
        # qid -> {topic, seen, correct, repetition, next_review, ease}
        "questions": {},
        # บันทึกการทำ quiz ย้อนหลัง
        "quiz_log": [],
        # คะแนนที่กรอกไว้ (ดิบ) — subject_code -> คะแนน
        "scores": {},
        # YYYY-MM-DD -> ชั่วโมงที่อ่านจริงรวมทั้งวัน (คู่กับ `S.days` ฝั่งแอป)
        "study_log": {},
        # YYYY-MM-DD -> [{topic, kind, hours}] รายบล็อกที่ทำจริงในวันนั้น
        # (คู่กับ `S.log` ฝั่งแอป) — ตารางต้องรู้ว่าวันนี้ลงมือหัวข้อไหนไปแล้ว
        "day_log": {},
    }


class ProgressStore:
    def __init__(self, path: str | Path):
        self.path = resolve_path(path)
        self.data = self._load()

    # ------------------------------------------------------------- io
    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return _empty()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            # ไฟล์เสีย — เริ่มใหม่ดีกว่าพัง แต่เก็บของเดิมไว้ดู
            backup = self.path.with_suffix(".corrupt.json")
            try:
                self.path.replace(backup)
            except OSError:
                pass
            return _empty()

        base = _empty()
        base.update(data)
        base["version"] = SCHEMA_VERSION
        return base

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")

    # --------------------------------------------------------- topics
    def topic(self, topic_code: str) -> Dict[str, Any]:
        return self.data["topics"].get(topic_code, {})

    def set_topic(self, topic_code: str, **fields: Any) -> None:
        rec = self.data["topics"].setdefault(topic_code, {})
        rec.update(fields)

    def is_learned(self, topic_code: str) -> bool:
        return bool(self.topic(topic_code).get("learned_on"))

    def add_topic_hours(
        self,
        topic_code: str,
        hours: float,
        total_hours: float,
        on: date,
        intervals: list | None = None,
        kind: str = "learn",
    ) -> bool:
        """บันทึกชั่วโมงที่อ่านหัวข้อนี้ — ครบชั่วโมงแล้วเข้าคิวทบทวนให้เอง.

        คืน True ถ้าหัวข้อนี้เพิ่งอ่านจบในครั้งนี้

        ทำหน้าที่เดียวกับ `completeBlock()` ฝั่งแอปเป๊ะ ๆ รวมถึงชื่อฟิลด์
        (`hours_done` ↔ `hoursDone`) — ต้องแก้พร้อมกันทั้งสองฝั่งเสมอ
        ไม่งั้นตารางอ่านจาก CLI กับจากแอปจะเดินคนละทาง
        """
        from . import srs

        rec = self.data["topics"].setdefault(topic_code, {})
        done = round(float(rec.get("hours_done", 0.0)) + float(hours), 2)
        rec["hours_done"] = done
        just_finished = False
        if done >= total_hours - 0.001 and not rec.get("learned_on"):
            rec.update(srs.first_schedule(on, intervals))
            rec["hours_done"] = done   # first_schedule ไม่รู้จักฟิลด์นี้
            just_finished = True
        self.log_study(on, float(hours))
        self.data["day_log"].setdefault(on.isoformat(), []).append(
            {"topic": topic_code, "kind": kind, "hours": float(hours)}
        )
        return just_finished

    def learned_topics(self) -> Dict[str, Dict[str, Any]]:
        return {k: v for k, v in self.data["topics"].items() if v.get("learned_on")}

    def due_reviews(self, on: date) -> list:
        """หัวข้อที่ถึงคิวทบทวน ณ วันที่กำหนด (เรียงจากค้างนานสุด)."""
        due = []
        for code, rec in self.data["topics"].items():
            nxt = rec.get("next_review")
            if not nxt:
                continue
            if parse_date(nxt) <= on:
                due.append((parse_date(nxt), code, rec))
        due.sort(key=lambda x: x[0])
        return [(code, rec) for _, code, rec in due]

    # ---------------------------------------------------------- mastery
    def mastery(self, topic_code: str, default: float) -> float:
        """ความแม่นของหัวข้อ 0-100 = ตอบถูกกี่ % ของข้อที่เคยทำในหัวข้อนั้น.

        คำนวณสด ๆ จากสถิติรายข้อ ไม่เก็บเป็นฟิลด์แยก — เพราะฝั่งแอป
        (`masteryOf` ใน tcas_app.html) คิดแบบนี้ ถ้าฝั่งนี้เก็บค่าสะสมของตัวเอง
        สองฝั่งจะแยกกันทันทีที่ทำ quiz และไม่มีทางไล่กลับมาตรงกันได้
        (ของเดิมเป็น EWMA ที่ขึ้นกับ "ลำดับ" ที่ตอบด้วย จึงทำซ้ำไม่ได้เลย)
        """
        seen = ok = 0
        for rec in self.data["questions"].values():
            if rec.get("topic") != topic_code:
                continue
            seen += int(rec.get("seen", 0))
            ok += int(rec.get("correct", 0))
        return 100.0 * ok / seen if seen else float(default)

    def subject_mastery(self, subject_code: str, topics: list, default: float) -> float:
        """ค่าเฉลี่ยความแม่นของวิชา ถ่วงด้วยน้ำหนักหัวข้อ."""
        num = den = 0.0
        for t in topics:
            w = float(t.weight)
            num += w * self.mastery(t.code, default)
            den += w
        return num / den if den else default

    # -------------------------------------------------------- questions
    def question(self, qid: str) -> Dict[str, Any]:
        return self.data["questions"].get(qid, {})

    def set_question(self, qid: str, **fields: Any) -> None:
        rec = self.data["questions"].setdefault(qid, {})
        rec.update(fields)

    # ------------------------------------------------------------ misc
    def log_quiz(self, entry: Dict[str, Any]) -> None:
        self.data["quiz_log"].append(entry)

    def day_entries(self, day: date) -> list:
        """บล็อกที่ทำไปแล้วในวันนั้น — ว่างได้ (ไฟล์เก่าไม่มีคีย์นี้)."""
        return list((self.data.get("day_log") or {}).get(day.isoformat()) or [])

    def log_study(self, day: date, hours: float) -> None:
        key = day.isoformat()
        self.data["study_log"][key] = round(
            float(self.data["study_log"].get(key, 0.0)) + hours, 2
        )

    def set_score(self, subject_code: str, score: float) -> None:
        self.data["scores"][subject_code] = float(score)

    def scores(self) -> Dict[str, float]:
        return dict(self.data["scores"])
