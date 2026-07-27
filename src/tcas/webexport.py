"""รวมข้อมูลทั้งระบบเป็น JSON ก้อนเดียว แล้วฝังลงหน้าเว็บ.

หน้าเว็บ (`web/tcas_app.html`) เป็นไฟล์ template ที่มีตัวคั่น
`/*__TCAS_DATA__*/` อยู่ข้างใน — ตอน export เราแทนที่ตรงนั้นด้วย JSON จริง
ได้ไฟล์ HTML ไฟล์เดียวที่เปิดได้เลย ไม่ต้องมีเซิร์ฟเวอร์ ไม่ต้องต่อเน็ต

ข้อมูลที่ฝัง = ตารางอ่าน + ตารางทดสอบ + คลังข้อสอบ + วันสอบ + คณะ
รันใหม่เมื่อไรก็ได้เมื่อแก้ config หรือเพิ่มข้อสอบ:

    python tcas_cli.py export
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import planner, ranking, scoring, syllabus, testplan
from .config import REPO_ROOT, exam_dates, parse_date, resolve_path
from .models import StudyDay

# ตัวคั่นกินค่า null ที่ตามมาด้วย เพื่อให้ผลลัพธ์เป็น `const DATA = {...};`
# ไม่ใช่ `const DATA = {...} null;` ซึ่งเป็น syntax error
# template ดิบ (ที่ยังไม่ได้ฝังข้อมูล) จึงยังเป็น JS ที่ถูกต้อง เปิดดูโครงหน้าได้
DATA_MARKER = "/*__TCAS_DATA__*/null"
DEFAULT_TEMPLATE = REPO_ROOT / "web" / "tcas_app.html"
DEFAULT_OUTPUT = REPO_ROOT / "web" / "tcas_app.build.html"


def _day_payload(sd: StudyDay) -> Dict[str, Any]:
    return {
        "date": sd.day.isoformat(),
        "hours": round(sd.hours, 2),
        "note": sd.note,
        "blocks": [
            {
                "subject": b.subject_code,
                "subjectName": b.subject_name,
                "topic": b.topic_code,
                "topicName": b.topic_name,
                "hours": round(b.hours, 2),
                "kind": b.kind,
                "repetition": b.repetition,
            }
            for b in sd.blocks
        ],
    }


def build_payload(
    cfg: Dict[str, Any],
    store,
    programs: Optional[Dict[str, Any]],
    bank: Dict[str, Any],
    start: date,
    horizon_days: int = 400,
) -> Dict[str, Any]:
    """สร้าง dict ที่จะกลายเป็น JSON ฝังในหน้าเว็บ."""
    plan = planner.generate_plan(cfg, store, start=start, max_days=horizon_days)
    tests = testplan.generate(cfg, plan, start)

    subjects = {
        code: {
            "name": subj.name,
            "short": subj.label,
            "exam": subj.exam,
            "group": subj.group,
            "maxScore": subj.max_score,
            "hours": round(subj.total_hours, 1),
            "topics": [
                {
                    "code": t.code,
                    "name": t.name,
                    "weight": t.weight,
                    "hours": t.hours,
                }
                for t in subj.topics
            ],
        }
        for code, subj in syllabus.SUBJECTS.items()
    }

    questions = [
        {
            "qid": q.qid,
            "subject": q.subject_code,
            "topic": q.topic_code,
            "stem": q.stem,
            "choices": list(q.choices),
            "answer": q.answer,
            "explanation": q.explanation,
            "difficulty": q.difficulty,
        }
        for q in bank.values()
    ]

    exams = [
        {
            "key": key,
            "name": spec["name"],
            "date": spec["date"].isoformat(),
            "verified": spec["verified"],
        }
        for key, spec in exam_dates(cfg).items()
    ]

    milestones = [
        {"date": parse_date(m["date"]).isoformat(), "label": str(m.get("label", ""))}
        for m in (cfg.get("milestones") or [])
    ]

    program_list: List[Dict[str, Any]] = []
    if programs:
        for c in ranking.rank(programs, None):
            program_list.append(
                {
                    "code": c.code,
                    "name": c.name,
                    "faculty": c.faculty,
                    "seats": c.seats,
                    "projected": c.projected_cutoff,
                    "trend": c.trend,
                    "verified": c.verified,
                }
            )

    return {
        "generatedAt": date.today().isoformat(),
        "startDate": start.isoformat(),
        "student": cfg.get("student") or {},
        "exams": exams,
        "milestones": milestones,
        "weights": scoring.group_weights(cfg),
        "groupLabels": scoring.GROUP_LABELS,
        "minimums": (cfg.get("kaspot") or {}).get("minimums") or {},
        "subjects": subjects,
        "plan": [_day_payload(sd) for sd in plan],
        "tests": [
            {
                "date": e.day.isoformat(),
                "kind": e.kind,
                "kindLabel": testplan.KIND_LABELS.get(e.kind, e.kind),
                "title": e.title,
                "subjects": e.subjects,
                "topics": e.topics,
                "questions": e.questions,
                "minutes": e.minutes,
                "note": e.note,
            }
            for e in tests
        ],
        "questions": questions,
        "programs": program_list,
    }


def render(payload: Dict[str, Any], template: str | Path | None = None) -> str:
    """ฝัง payload ลง template คืนเป็นสตริง HTML ที่สมบูรณ์."""
    path = resolve_path(template) if template else DEFAULT_TEMPLATE
    if not path.exists():
        raise FileNotFoundError(f"ไม่พบไฟล์ template: {path}")
    html = path.read_text(encoding="utf-8")
    if DATA_MARKER not in html:
        raise ValueError(
            f"template ไม่มีตัวคั่น {DATA_MARKER} — ใส่ไว้ตรงที่ต้องการให้ข้อมูลไปอยู่"
        )
    # </script> ใน string ของ JSON จะไปปิด <script> ของหน้าเว็บก่อนเวลา
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return html.replace(DATA_MARKER, blob)


def write(html: str, output: str | Path | None = None) -> Path:
    path = resolve_path(output) if output else DEFAULT_OUTPUT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path
