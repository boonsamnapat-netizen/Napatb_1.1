"""คลังข้อสอบ + การรันชุดข้อสอบ + อัปเดตสถิติ.

คลังข้อสอบเก็บเป็น YAML หนึ่งไฟล์ต่อวิชาใน `data/tcas/questions/`
เพิ่มข้อสอบได้โดยแก้ YAML อย่างเดียว ไม่ต้องแตะโค้ด — ดูรูปแบบใน docs/TCAS_SYSTEM.md

โหมดเลือกข้อ
  due   — ข้อที่เคยตอบผิด/ถึงคิวทบทวนตาม SRS (ค่าเริ่มต้น ถ้ามีพอ)
  new   — ข้อที่ยังไม่เคยทำ
  wrong — เฉพาะข้อที่เคยตอบผิดล่าสุด
  mixed — ผสม due ก่อน แล้วเติมด้วย new
  all   — สุ่มจากทั้งคลัง
"""

from __future__ import annotations

import random
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from . import srs, syllabus
from .config import parse_date, resolve_path
from .models import CHOICE_LETTERS, Question, QuizResult
from .store import ProgressStore


class BankError(Exception):
    """คลังข้อสอบมีปัญหา (ไฟล์เสีย/เฉลยไม่ตรงตัวเลือก/หัวข้อไม่มีจริง)."""


def load_bank(questions_dir: str | Path) -> Dict[str, Question]:
    """อ่าน YAML ทุกไฟล์ในโฟลเดอร์ คืน {qid: Question} พร้อมตรวจความถูกต้อง."""
    d = resolve_path(questions_dir)
    if not d.exists():
        return {}

    bank: Dict[str, Question] = {}
    for path in sorted(d.glob("*.yaml")) + sorted(d.glob("*.yml")):
        with open(path, "r", encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
        subject_code = doc.get("subject")
        if not subject_code:
            raise BankError(f"{path.name}: ไม่ได้ระบุ 'subject'")
        try:
            syllabus.get_subject(subject_code)
        except KeyError as exc:
            raise BankError(f"{path.name}: {exc}") from exc

        for i, raw in enumerate(doc.get("questions") or [], start=1):
            qid = str(raw.get("qid") or f"{subject_code}_{i:03d}")
            if qid in bank:
                raise BankError(f"{path.name}: qid ซ้ำ '{qid}'")
            choices = list(raw.get("choices") or [])
            answer = int(raw.get("answer", -1))
            if len(choices) < 2:
                raise BankError(f"{qid}: ต้องมีอย่างน้อย 2 ตัวเลือก")
            if not 0 <= answer < len(choices):
                raise BankError(
                    f"{qid}: 'answer' = {answer} ไม่อยู่ในช่วงตัวเลือก 0-{len(choices) - 1}"
                )
            topic_code = str(raw.get("topic", ""))
            if topic_code:
                subj, topic = syllabus.find_topic(topic_code)
                if topic is None:
                    raise BankError(f"{qid}: ไม่รู้จักหัวข้อ '{topic_code}'")
                if subj.code != subject_code:
                    raise BankError(
                        f"{qid}: หัวข้อ '{topic_code}' อยู่ในวิชา '{subj.code}' "
                        f"ไม่ใช่ '{subject_code}'"
                    )
            bank[qid] = Question(
                qid=qid,
                subject_code=subject_code,
                topic_code=topic_code,
                stem=str(raw.get("stem", "")).strip(),
                choices=[str(c) for c in choices],
                answer=answer,
                explanation=str(raw.get("explanation", "")).strip(),
                difficulty=int(raw.get("difficulty", 2)),
                source=str(raw.get("source", "")),
            )
    return bank


def bank_stats(bank: Dict[str, Question]) -> Dict[str, Dict[str, int]]:
    """นับข้อสอบต่อวิชา/ต่อหัวข้อ — ใช้ดูว่าคลังยังขาดตรงไหน."""
    out: Dict[str, Dict[str, int]] = {}
    for q in bank.values():
        sub = out.setdefault(q.subject_code, {})
        sub["total"] = sub.get("total", 0) + 1
        sub[q.topic_code or "(ไม่ระบุหัวข้อ)"] = sub.get(q.topic_code or "(ไม่ระบุหัวข้อ)", 0) + 1
    return out


def select_questions(
    bank: Dict[str, Question],
    store: ProgressStore,
    on: date,
    subject: Optional[str] = None,
    topic: Optional[str] = None,
    count: int = 10,
    mode: str = "mixed",
    rng: Optional[random.Random] = None,
) -> List[Question]:
    """เลือกข้อสอบตามโหมด — คืนลิสต์ที่สลับลำดับแล้ว."""
    rng = rng or random.Random()
    pool = [
        q
        for q in bank.values()
        if (subject is None or q.subject_code == subject)
        and (topic is None or q.topic_code == topic)
    ]
    if not pool:
        return []

    def is_due(q: Question) -> bool:
        rec = store.question(q.qid)
        nxt = rec.get("next_review")
        return bool(nxt) and parse_date(nxt) <= on

    def is_new(q: Question) -> bool:
        return not store.question(q.qid).get("seen")

    def was_wrong(q: Question) -> bool:
        rec = store.question(q.qid)
        return bool(rec.get("seen")) and int(rec.get("repetition", 0)) == 0

    if mode == "new":
        chosen = [q for q in pool if is_new(q)]
    elif mode == "due":
        chosen = [q for q in pool if is_due(q)]
    elif mode == "wrong":
        chosen = [q for q in pool if was_wrong(q)]
    elif mode == "all":
        chosen = list(pool)
    else:  # mixed — ทบทวนที่ถึงคิวก่อน แล้วเติมด้วยข้อใหม่ แล้วค่อยที่เหลือ
        due = [q for q in pool if is_due(q)]
        fresh = [q for q in pool if is_new(q)]
        rest = [q for q in pool if q not in due and q not in fresh]
        rng.shuffle(due)
        rng.shuffle(fresh)
        rng.shuffle(rest)
        chosen = (due + fresh + rest)[:count]
        return chosen

    rng.shuffle(chosen)
    return chosen[:count]


def grade(
    questions: List[Question],
    answers: List[Optional[int]],
    store: ProgressStore,
    cfg: Dict[str, Any],
    on: date,
) -> QuizResult:
    """ตรวจคำตอบ อัปเดต SRS ของข้อสอบและความแม่นของหัวข้อ.

    `answers[i]` = index ตัวเลือกที่ตอบ หรือ None ถ้าข้าม (นับเป็นผิด)
    """
    intervals = list(
        (cfg.get("study") or {}).get("review_intervals_days") or srs.DEFAULT_INTERVALS
    )
    baseline = float(cfg.get("baseline_mastery", 35.0))

    correct_count = 0
    wrong: List[str] = []
    per_topic: Dict[str, List[int]] = {}
    subject_code = questions[0].subject_code if questions else ""

    for q, given in zip(questions, answers):
        ok = given is not None and given == q.answer
        correct_count += int(ok)
        if not ok:
            wrong.append(q.qid)

        # --- สถิติข้อสอบ + คิวทบทวนข้อนี้
        rec = dict(store.question(q.qid))
        rec["seen"] = int(rec.get("seen", 0)) + 1
        rec["correct"] = int(rec.get("correct", 0)) + int(ok)
        rec.update(srs.schedule(rec, correct=ok, on=on, intervals=intervals))
        store.set_question(q.qid, **rec)

        # --- ความแม่นของหัวข้อ
        if q.topic_code:
            slot = per_topic.setdefault(q.topic_code, [0, 0])
            slot[0] += int(ok)
            slot[1] += 1
            current = store.mastery(q.topic_code, baseline)
            store.set_topic(
                q.topic_code, mastery=srs.update_mastery(current, ok)
            )
            # ตอบผิดหัวข้อที่อ่านไปแล้ว = ลืม -> ดึงกลับมาทบทวนพรุ่งนี้
            if not ok and store.is_learned(q.topic_code):
                trec = dict(store.topic(q.topic_code))
                store.set_topic(
                    q.topic_code,
                    **srs.schedule(trec, correct=False, on=on, intervals=intervals),
                )

    result = QuizResult(
        subject_code=subject_code,
        total=len(questions),
        correct=correct_count,
        wrong_qids=wrong,
        per_topic=per_topic,
    )
    store.log_quiz(
        {
            "date": on.isoformat(),
            "subject": subject_code,
            "total": result.total,
            "correct": result.correct,
            "pct": round(result.pct, 1),
        }
    )
    return result


def render_question(q: Question, index: int, total: int) -> str:
    """ข้อสอบหนึ่งข้อในรูปข้อความ (ใช้ทั้งบนเทอร์มินัลและ Telegram)."""
    lines = [f"ข้อ {index}/{total}  [{q.subject_code}]", "", q.stem, ""]
    for i, choice in enumerate(q.choices):
        letter = CHOICE_LETTERS[i] if i < len(CHOICE_LETTERS) else str(i + 1)
        lines.append(f"  {letter}. {choice}")
    return "\n".join(lines)


def parse_answer(raw: str, n_choices: int) -> Optional[int]:
    """รับได้ทั้ง 'ก'/'ข'/... และ '1'/'2'/... — คืน index หรือ None ถ้าข้าม."""
    s = (raw or "").strip()
    if not s:
        return None
    if s in CHOICE_LETTERS:
        idx = CHOICE_LETTERS.index(s)
        return idx if idx < n_choices else None
    if s.isdigit():
        idx = int(s) - 1
        return idx if 0 <= idx < n_choices else None
    return None
