"""เรนเดอร์รายงานภาษาไทย — ใช้ทั้งบนเทอร์มินัลและส่ง Telegram.

ข้อความออกแบบให้อ่านรู้เรื่องทั้งสองที่ จึงใช้ HTML tag แค่ <b> กับ <code>
ซึ่ง Telegram รองรับ และบนเทอร์มินัลก็ยังพออ่านได้
"""

from __future__ import annotations

import html
from datetime import date
from typing import Any, Dict, List, Optional

from . import planner, ranking, scoring, syllabus
from .config import exam_dates, parse_date
from .models import ProgramChance, QuizResult, ScoreCard, StudyDay

THAI_WEEKDAYS = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
THAI_MONTHS = [
    "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]

BAND_ICONS = {
    ranking.BAND_SAFE_LABEL: "🟢",
    ranking.BAND_LIKELY_LABEL: "🟡",
    ranking.BAND_REACH_LABEL: "🟠",
    ranking.BAND_FAR_LABEL: "🔴",
    ranking.BAND_NODATA_LABEL: "⚪",
}


def thai_date(d: date, with_weekday: bool = True) -> str:
    """1 ส.ค. 2569 (ศุกร์) — ปี พ.ศ."""
    core = f"{d.day} {THAI_MONTHS[d.month - 1]} {d.year + 543}"
    return f"{core} ({THAI_WEEKDAYS[d.weekday()]})" if with_weekday else core


def fmt_hours(h: float) -> str:
    hours = int(h)
    minutes = int(round((h - hours) * 60))
    if hours and minutes:
        return f"{hours} ชม. {minutes} นาที"
    if hours:
        return f"{hours} ชม."
    return f"{minutes} นาที"


def _esc(s: str) -> str:
    return html.escape(str(s), quote=False)


# ------------------------------------------------------------- นับถอยหลัง
def countdown(cfg: Dict[str, Any], on: date) -> str:
    lines = ["<b>⏳ นับถอยหลัง</b>"]
    for spec in exam_dates(cfg).values():
        days = (spec["date"] - on).days
        mark = "" if spec["verified"] else " ⚠️"
        if days < 0:
            lines.append(f"• {_esc(spec['name'])} — สอบไปแล้ว")
        elif days == 0:
            lines.append(f"• <b>{_esc(spec['name'])} — สอบวันนี้!</b>")
        else:
            lines.append(
                f"• {_esc(spec['name'])} — เหลือ <b>{days}</b> วัน "
                f"({thai_date(spec['date'], with_weekday=False)}){mark}"
            )
    if any(not s["verified"] for s in exam_dates(cfg).values()):
        lines.append("<i>⚠️ = วันสอบยังไม่ยืนยัน ตรวจกับ mytcas.com</i>")
    return "\n".join(lines)


def upcoming_milestones(cfg: Dict[str, Any], on: date, within_days: int = 45) -> str:
    """หมุดหมายสำคัญ (วันสมัคร/ยื่นคะแนน) ที่ใกล้เข้ามา."""
    items = []
    for m in cfg.get("milestones") or []:
        d = parse_date(m["date"])
        days = (d - on).days
        if 0 <= days <= within_days:
            items.append((days, d, str(m.get("label", ""))))
    if not items:
        return ""
    items.sort()
    lines = ["<b>📌 หมุดหมายที่ใกล้ถึง</b>"]
    for days, d, label in items:
        when = "วันนี้" if days == 0 else f"อีก {days} วัน"
        lines.append(f"• {_esc(label)} — {when} ({thai_date(d, with_weekday=False)})")
    return "\n".join(lines)


# ------------------------------------------------------------ ตารางรายวัน
def study_day(sd: StudyDay, header: bool = True) -> str:
    lines = []
    if header:
        lines.append(f"<b>📚 ตารางวันที่ {thai_date(sd.day)}</b>")
    if not sd.blocks:
        lines.append(f"<i>{_esc(sd.note or 'ไม่มีตารางวันนี้')}</i>")
        return "\n".join(lines)

    learn = [b for b in sd.blocks if b.kind == "learn"]
    review = [b for b in sd.blocks if b.kind == "review"]

    if review:
        lines.append(f"<b>ทบทวน</b> ({fmt_hours(sum(b.hours for b in review))})")
        for b in review:
            lines.append(
                f"  🔁 {_esc(b.topic_name)} <code>[{_esc(b.subject_code)}]</code> "
                f"— {fmt_hours(b.hours)} · ครั้งที่ {b.repetition}"
            )
    if learn:
        lines.append(f"<b>อ่านใหม่</b> ({fmt_hours(sum(b.hours for b in learn))})")
        for b in learn:
            lines.append(
                f"  📖 {_esc(b.topic_name)} <code>[{_esc(b.subject_code)}]</code> "
                f"— {fmt_hours(b.hours)}"
            )
    lines.append(f"<b>รวม {fmt_hours(sd.hours)}</b>")
    return "\n".join(lines)


def plan_summary(days: List[StudyDay], limit: int = 7) -> str:
    """สรุปตารางหลายวัน — ใช้กับคำสั่ง plan."""
    lines = []
    shown = [d for d in days if d.blocks][:limit]
    for sd in shown:
        lines.append(study_day(sd))
        lines.append("")
    total = sum(d.hours for d in days)
    active = sum(1 for d in days if d.blocks)
    lines.append(
        f"<b>รวมทั้งแผน</b> {len(days)} วัน · อ่านจริง {active} วัน · {fmt_hours(total)}"
    )
    return "\n".join(lines).strip()


# --------------------------------------------------------------- ความคืบหน้า
def coverage(cfg: Dict[str, Any], store) -> str:
    data = planner.coverage(cfg, store)
    lines = ["<b>📊 ความคืบหน้ารายวิชา</b>"]
    for code in sorted(data, key=lambda c: -data[c]["pct"]):
        d = data[code]
        bar = _bar(d["pct"])
        lines.append(
            f"{bar} <b>{d['pct']:5.1f}%</b> {_esc(d['name'])}\n"
            f"      หัวข้อ {d['topics_done']}/{d['topics_total']} · "
            f"{d['hours_done']:.0f}/{d['hours_total']:.0f} ชม. · ความแม่น {d['mastery']:.0f}%"
        )
    return "\n".join(lines)


def _bar(pct: float, width: int = 10) -> str:
    filled = int(round(pct / 100.0 * width))
    return "▰" * filled + "▱" * (width - filled)


# ------------------------------------------------------------------- quiz
def quiz_result(result: QuizResult, bank: Dict[str, Any]) -> str:
    subj_name = (
        syllabus.SUBJECTS[result.subject_code].name
        if result.subject_code in syllabus.SUBJECTS
        else result.subject_code
    )
    verdict = (
        "เยี่ยม 🎉" if result.pct >= 80
        else "ผ่านเกณฑ์ 👍" if result.pct >= 60
        else "ต้องกลับไปทบทวน 📕"
    )
    lines = [
        f"<b>📝 ผลชุดข้อสอบ — {_esc(subj_name)}</b>",
        f"ถูก <b>{result.correct}/{result.total}</b> ({result.pct:.0f}%) — {verdict}",
    ]

    if result.per_topic:
        lines.append("")
        lines.append("<b>แยกตามหัวข้อ</b>")
        for topic_code, (ok, total) in sorted(
            result.per_topic.items(), key=lambda kv: kv[1][0] / kv[1][1]
        ):
            _, topic = syllabus.find_topic(topic_code)
            name = topic.name if topic else topic_code
            icon = "✅" if ok == total else ("⚠️" if ok else "❌")
            lines.append(f"  {icon} {_esc(name)} — {ok}/{total}")

    if result.wrong_qids:
        lines.append("")
        lines.append(f"<b>ข้อที่ตอบผิด ({len(result.wrong_qids)})</b> — ถูกดันเข้าคิวทบทวนพรุ่งนี้แล้ว")
        for qid in result.wrong_qids:
            q = bank.get(qid)
            if not q:
                continue
            stem = q.stem if len(q.stem) <= 90 else q.stem[:87] + "..."
            lines.append(f"  • {_esc(stem)}")
            lines.append(f"    เฉลย: <b>{_esc(q.answer_label())}</b>")
            if q.explanation:
                lines.append(f"    <i>{_esc(q.explanation)}</i>")
    return "\n".join(lines)


# ------------------------------------------------------------------ คะแนน
def score_card(card: ScoreCard, cfg: Dict[str, Any]) -> str:
    weights = scoring.group_weights(cfg)
    lines = [f"<b>🎯 คะแนนรวม กสพท: {card.total:.2f} / 100</b>", ""]
    for group in ["tpat1", "science", "math1", "english", "thai", "social"]:
        if group not in card.breakdown:
            continue
        pct, weighted = card.breakdown[group]
        label = scoring.GROUP_LABELS.get(group, group)
        lines.append(
            f"• {_esc(label)}\n"
            f"    ทำได้ {pct:.1f}% × น้ำหนัก {weights.get(group, 0):.0f} = <b>{weighted:.2f}</b>"
        )

    lines.append("")
    if card.missing:
        names = ", ".join(syllabus.SUBJECTS[c].name for c in card.missing if c in syllabus.SUBJECTS)
        lines.append(f"⚠️ ยังไม่ได้กรอกคะแนน: {_esc(names)} (นับเป็น 0 ในคะแนนรวม)")
    if card.failures:
        lines.append("<b>❌ ตกเกณฑ์ขั้นต่ำ</b>")
        for f in card.failures:
            lines.append(f"  • {_esc(f)}")
        lines.append("<i>ตกเกณฑ์แม้ข้อเดียว = ไม่ผ่านการคัดเลือก ไม่ว่าคะแนนรวมจะสูงแค่ไหน</i>")
    elif not card.missing:
        lines.append("✅ ผ่านเกณฑ์ขั้นต่ำทุกวิชา")
    return "\n".join(lines)


# ------------------------------------------------------------ จัดอันดับคณะ
def program_ranking(
    chances: List[ProgramChance],
    my_score: Optional[float],
    limit: int = 20,
) -> str:
    head = f"<b>🏥 โอกาสติดคณะ (คะแนนที่ใช้: {my_score:.2f})</b>" if my_score is not None else "<b>🏥 คะแนนต่ำสุดย้อนหลัง</b>"
    lines = [head, ""]
    for c in chances[:limit]:
        icon = BAND_ICONS.get(c.band, "⚪")
        warn = " ⚠️" if not c.verified else ""
        proj = f"{c.projected_cutoff:.2f}" if c.projected_cutoff is not None else "—"
        line = f"{icon} <b>{proj}</b> {_esc(c.name)}{warn}"
        if c.margin is not None:
            sign = "+" if c.margin >= 0 else ""
            line += f"\n      ห่าง {sign}{c.margin:.2f} · {c.band}"
            if c.trend:
                line += f" · แนวโน้ม {c.trend:+.2f}/ปี"
        lines.append(line)

    lines.append("")
    lines.append(
        "🟢 ปลอดภัย (+3 ขึ้นไป) · 🟡 ลุ้น (0 ถึง +3) · "
        "🟠 ท้าทาย (−3 ถึง 0) · 🔴 เกินเอื้อม"
    )
    if any(not c.verified for c in chances[:limit]):
        lines.append(
            "<i>⚠️ = คะแนนต่ำสุดยังเป็นค่าประมาณ ยังไม่ได้ยืนยันกับประกาศจริง "
            "แก้ได้ที่ config/tcas_programs.yaml</i>"
        )
    return "\n".join(lines)


def order_suggestion(chances: List[ProgramChance], limit: int = 10) -> str:
    picks = ranking.suggested_order(chances, limit=limit)
    lines = [
        "<b>📋 ลำดับที่แนะนำสำหรับรอบ 3</b>",
        "<i>ระบบจัดให้ตามลำดับที่เลือก จึงวางคณะที่อยากได้จริง (ท้าทาย) ไว้บนสุด "
        "แล้วปิดท้ายด้วยคณะปลอดภัยกันพลาด</i>",
        "",
    ]
    for i, c in enumerate(picks, start=1):
        icon = BAND_ICONS.get(c.band, "⚪")
        proj = f"{c.projected_cutoff:.2f}" if c.projected_cutoff is not None else "—"
        lines.append(f"{i}. {icon} {_esc(c.name)} (คาด {proj})")
    return "\n".join(lines)


# ------------------------------------------------------ สรุปรายวันสำหรับ bot
def daily_brief(
    cfg: Dict[str, Any],
    store,
    sd: StudyDay,
    on: date,
    include_coverage: bool = True,
) -> str:
    """ข้อความแจ้งเตือนตอนเช้า — นับถอยหลัง + ตารางวันนี้ + คิวทบทวน."""
    name = ((cfg.get("student") or {}).get("name") or "").strip()
    greeting = f"สวัสดีตอนเช้า{' คุณ ' + name if name else ''} ☀️"
    parts = [f"<b>{_esc(greeting)}</b>", "", countdown(cfg, on), ""]

    milestones = upcoming_milestones(cfg, on)
    if milestones:
        parts += [milestones, ""]

    parts.append(study_day(sd))

    due = store.due_reviews(on)
    if due:
        parts += ["", f"<b>🔁 ค้างทบทวน {len(due)} หัวข้อ</b>"]
        for code, _rec in due[:5]:
            _, topic = syllabus.find_topic(code)
            if topic:
                parts.append(f"  • {_esc(topic.name)}")
        if len(due) > 5:
            parts.append(f"  <i>…และอีก {len(due) - 5} หัวข้อ</i>")

    if include_coverage:
        parts += ["", coverage(cfg, store)]

    return "\n".join(parts)
