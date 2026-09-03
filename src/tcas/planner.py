"""สร้างตารางอ่านหนังสือรายวันจนถึงวันสอบ.

ตรรกะหลัก
  1. แต่ละวันมีเวลาว่างตาม `study.hours_by_weekday` (หักวันหยุดใน `days_off`)
  2. กันเวลาส่วนหนึ่ง (`study.review_share`) ไว้ทบทวนหัวข้อที่ถึงคิว SRS ก่อนเสมอ
     — ทบทวนสำคัญกว่าอ่านใหม่ เพราะอ่านแล้วลืมคือเสียเวลาเปล่า
  3. เวลาที่เหลือใช้อ่านหัวข้อใหม่ โดยเลือกหัวข้อที่ "คุ้มที่สุด" ก่อน:

         คะแนน = น้ำหนักหัวข้อ × น้ำหนักกลุ่มใน กสพท × (1 − ความแม่น) × ความเร่งด่วน

     ความเร่งด่วน = ชั่วโมงที่ยังต้องอ่านของวิชานั้น ÷ ชั่วโมงว่างที่เหลือก่อนวันสอบ
     ของวิชานั้น — ทำให้ TPAT1 (สอบ ธ.ค.) ถูกดันขึ้นมาก่อน A-Level (สอบ มี.ค.)
     โดยอัตโนมัติ ไม่ต้องฮาร์ดโค้ดลำดับ

ตารางที่ได้เป็นการ "จำลองล่วงหน้า" — สมมติว่าทบทวนแล้วจำได้ทุกครั้ง เวลาใช้จริง
ให้ยึด `today` ที่อ่านสถานะจริงจาก store แทน
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from . import srs, syllabus
from .config import parse_date
from .models import StudyBlock, StudyDay
from .store import ProgressStore

WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def hours_for(day: date, cfg: Dict[str, Any]) -> float:
    """ชั่วโมงที่อ่านได้ในวันนั้น (0 ถ้าเป็นวันหยุด)."""
    study = cfg.get("study") or {}
    days_off = {str(d) for d in (study.get("days_off") or [])}
    if day.isoformat() in days_off:
        return 0.0
    table = study.get("hours_by_weekday") or {}
    return float(table.get(WEEKDAY_KEYS[day.weekday()], 0.0))


def _subject_deadlines(cfg: Dict[str, Any]) -> Dict[str, date]:
    """วันสอบของแต่ละวิชา.

    ใช้ `subject_schedule` ก่อนเสมอ เพราะ A-Level กระจายอยู่สองวัน
    (ชีวะ/ฟิสิกส์/ไทย/สังคม 13 มี.ค. · คณิต/อังกฤษ/เคมี 14 มี.ค.)
    ถ้าวิชาไหนไม่มีในตารางรายวิชา ค่อยถอยไปใช้วันรวมของสนามนั้น

    ⚠️ ต้องให้ผลตรงกับ `ST.deadlines` ฝั่งแอป (webexport.py ส่งมาจาก
    subject_schedule เหมือนกัน) — ถ้าสองฝั่งต่างกัน ตารางอ่านจะคนละชุด
    """
    from .config import exam_dates, subject_schedule

    exams = exam_dates(cfg)
    tpat1_date = exams.get("tpat1", {}).get("date")
    alevel_date = exams.get("alevel", {}).get("date")
    per_subject = subject_schedule(cfg)
    out: Dict[str, date] = {}
    for code, subj in syllabus.SUBJECTS.items():
        spec = per_subject.get(code)
        target = spec["date"] if spec else (
            tpat1_date if subj.exam == "tpat1" else alevel_date
        )
        if target:
            out[code] = target
    return out


def _group_weights(cfg: Dict[str, Any]) -> Dict[str, float]:
    """น้ำหนักของแต่ละกลุ่มวิชาในคะแนนรวม 100 ของ กสพท."""
    k = cfg.get("kaspot") or {}
    tpat1_w = float(k.get("tpat1_weight", 30.0))
    alevel_w = float(k.get("alevel_weight", 70.0))
    split = k.get("alevel_split") or {}
    weights = {"tpat1": tpat1_w}
    for group, share in split.items():
        weights[group] = alevel_w * float(share) / 100.0
    return weights


def _subject_weight(subject_code: str, group_weights: Dict[str, float]) -> float:
    """น้ำหนักต่อวิชา — กลุ่ม science มี 3 วิชา จึงหารสามให้เท่ากัน."""
    subj = syllabus.get_subject(subject_code)
    group_total = group_weights.get(subj.group, 1.0)
    n_in_group = len(syllabus.GROUPS.get(subj.group, [subject_code]))
    return group_total / max(n_in_group, 1)


def _cumulative_learn_hours(
    start: date, end: date, cfg: Dict[str, Any], learn_share: float
) -> Dict[date, float]:
    """ตารางสะสมชั่วโมงอ่าน 'ของใหม่' ตั้งแต่ `start` ถึงแต่ละวัน.

    คำนวณครั้งเดียวตอนเริ่ม แล้วหาช่วงใด ๆ ด้วยการลบ — เร็วกว่าไล่วันซ้ำทุกบล็อก
    """
    cum: Dict[date, float] = {}
    running = 0.0
    d = start
    while d <= end:
        cum[d] = running
        running += hours_for(d, cfg) * learn_share
        d += timedelta(days=1)
    cum[end + timedelta(days=1)] = running
    return cum


def _hours_between(cum: Dict[date, float], frm: date, to: date) -> float:
    """ชั่วโมงอ่านของใหม่ระหว่างสองวัน โดยใช้ตารางสะสม (clamp ที่ขอบ)."""
    if not cum:
        return 0.0
    lo, hi = min(cum), max(cum)
    a = cum[min(max(frm, lo), hi)]
    b = cum[min(max(to, lo), hi)]
    return max(0.0, b - a)


def _review_hours(topic_hours: float, repetition: int) -> float:
    """เวลาทบทวนหนึ่งครั้ง — ครั้งแรก ~25% ของเวลาอ่านรอบแรก แล้วสั้นลงเรื่อย ๆ."""
    base = topic_hours * 0.25 * (0.7 ** max(repetition - 1, 0))
    return max(0.25, round(base * 4) / 4)  # ปัดเป็นช่วงละ 15 นาที


def generate_plan(
    cfg: Dict[str, Any],
    store: ProgressStore,
    start: date,
    end: Optional[date] = None,
    subjects: Optional[List[str]] = None,
    max_days: int = 400,
) -> List[StudyDay]:
    """สร้างตารางตั้งแต่ `start` จนถึง `end` (ค่าเริ่มต้น = วันสอบสุดท้าย)."""
    study = cfg.get("study") or {}
    review_share = float(study.get("review_share", 0.25))
    learn_share = max(0.0, 1.0 - review_share)
    block_hours = float(study.get("block_hours", 1.5))
    intervals = list(study.get("review_intervals_days") or srs.DEFAULT_INTERVALS)
    baseline = float(cfg.get("baseline_mastery", 35.0))

    deadlines = _subject_deadlines(cfg)
    group_weights = _group_weights(cfg)

    if end is None:
        end = max(deadlines.values()) if deadlines else start + timedelta(days=180)
    if (end - start).days > max_days:
        end = start + timedelta(days=max_days)

    wanted = set(subjects) if subjects else set(syllabus.SUBJECTS)
    horizon = max([end] + list(deadlines.values())) if deadlines else end
    cum_hours = _cumulative_learn_hours(start, horizon, cfg, learn_share)

    # ---- สถานะจำลอง: หัวข้อไหนอ่านแล้ว / คิวทบทวนถัดไป
    sim: Dict[str, Dict[str, Any]] = {}
    pending: List[tuple] = []          # (subject, topic) ที่ยังไม่ได้อ่าน
    for subj, topic in syllabus.all_topics():
        if subj.code not in wanted:
            continue
        # วิชาที่เลยวันสอบไปแล้ว ตัดออก — ไม่งั้นเวลาว่างก่อนเส้นตายเป็น 0
        # ทำให้ความเร่งด่วนพุ่งค้างและวิชานั้นขึ้นบนสุดตลอดไป
        dl = deadlines.get(subj.code)
        if dl and dl < start:
            continue
        rec = dict(store.topic(topic.code))
        # ชั่วโมงที่ยังเหลือของหัวข้อ — หัวข้อที่อ่านค้างไว้ครึ่งทางต้องเหลือแค่ครึ่ง
        # ไม่ใช่นับใหม่ทั้งก้อน (ฝั่งแอปคิดแบบนี้มาตลอดผ่าน `hoursLeftOf`)
        left = round(max(0.0, topic.hours - float(rec.get("hours_done", 0.0))) * 4) / 4
        if left >= 0.25:
            pending.append((subj, replace(topic, hours=left)))
        if rec.get("next_review"):
            sim[topic.code] = rec

    days: List[StudyDay] = []
    cursor = start
    while cursor <= end:
        available = hours_for(cursor, cfg)
        # หักเวลาที่ลงบันทึกไว้แล้วของวันนั้นออก — อ่านไปครึ่งวันแล้ว ตารางที่เหลือ
        # ต้องเหลือแค่ส่วนที่ค้าง ไม่ใช่สั่งอ่านเต็มวันซ้ำ (ตรงกับฝั่งแอป)
        logged = sum(float(e.get("hours", 0.0)) for e in store.day_entries(cursor))
        capacity = max(0.0, available - logged)
        if capacity <= 0:
            note = "วันพัก" if available <= 0 else "ทำครบแล้ว"
            days.append(StudyDay(day=cursor, note=note))
            cursor += timedelta(days=1)
            continue

        sd = StudyDay(day=cursor)
        review_budget = capacity * review_share
        used_review = 0.0

        # ---------------------------------------------------- 1) ทบทวน
        due = [
            (parse_date(rec["next_review"]), code, rec)
            for code, rec in sim.items()
            if rec.get("next_review") and parse_date(rec["next_review"]) <= cursor
        ]
        due.sort(key=lambda x: x[0])
        for _, code, rec in due:
            subj, topic = syllabus.find_topic(code)
            if topic is None:
                continue
            need = _review_hours(topic.hours, int(rec.get("repetition", 0)) + 1)
            # หัวข้อใหญ่อาจกินเวลามากกว่าทั้งวัน — ตัดไม่ให้ล้นเวลาที่มีจริง
            need = min(need, capacity - used_review)
            if need < 0.25:
                break
            if used_review + need > review_budget and used_review > 0:
                break  # ค้างไว้ทบทวนพรุ่งนี้
            sd.blocks.append(
                StudyBlock(
                    subject_code=subj.code,
                    subject_name=subj.name,
                    topic_code=topic.code,
                    topic_name=topic.name,
                    hours=need,
                    kind="review",
                    repetition=int(rec.get("repetition", 0)) + 1,
                )
            )
            used_review += need
            # จำลองว่าทบทวนผ่าน
            rec.update(srs.schedule(rec, correct=True, on=cursor, intervals=intervals))

        # ---------------------------------------------------- 2) อ่านใหม่
        learn_budget = max(0.0, capacity - used_review)

        # ความเร่งด่วนรายวิชา — คำนวณวันละครั้ง (พอสำหรับการจัดลำดับ)
        urgency: Dict[str, float] = {}
        remaining: Dict[str, float] = {}
        for subj, topic in pending:
            remaining[subj.code] = remaining.get(subj.code, 0.0) + topic.hours
        for scode, hours_left in remaining.items():
            dl = deadlines.get(scode, end)
            avail = _hours_between(cum_hours, cursor, dl)
            urgency[scode] = min(5.0, max(0.1, hours_left / max(avail, 1.0)))

        def score(item) -> float:
            subj, topic = item
            mastery = store.mastery(topic.code, baseline)
            return (
                topic.weight
                * _subject_weight(subj.code, group_weights)
                * (1.0 - mastery / 100.0)
                * urgency.get(subj.code, 1.0)
            )

        # เรียงวันละครั้งเท่านั้น — ถ้าเรียงใหม่ในลูป หัวข้อที่เพิ่งแบ่งครึ่ง
        # จะเด้งกลับมาอันดับ 1 แล้วถูกจัดซ้ำในวันเดียวกัน (ฝั่งแอปเรียงนอกลูป)
        pending.sort(key=score, reverse=True)

        # หัวข้อที่ลงมือไปแล้ววันนี้ ดันไปท้ายคิว — ไม่งั้นพอบันทึกเสร็จปุ๊บ
        # มันยังคะแนนสูงสุดอยู่ (เพราะยังอ่านไม่จบ) แล้วเด้งกลับมาซ้ำทันที
        worked_today = {e.get("topic") for e in store.day_entries(cursor)}
        if worked_today:
            front = [x for x in pending if x[1].code not in worked_today]
            back = [x for x in pending if x[1].code in worked_today]
            pending[:] = front + back

        while learn_budget >= 0.25 and pending:
            subj, topic = pending[0]

            chunk = min(block_hours, topic.hours, learn_budget)
            chunk = round(chunk * 4) / 4
            if chunk < 0.25:
                break

            sd.blocks.append(
                StudyBlock(
                    subject_code=subj.code,
                    subject_name=subj.name,
                    topic_code=topic.code,
                    topic_name=topic.name,
                    hours=chunk,
                    kind="learn",
                )
            )
            learn_budget -= chunk

            # หัวข้อยาวกว่าหนึ่งบล็อก -> เหลือไว้อ่านต่อวันหลัง
            leftover = round((topic.hours - chunk) * 4) / 4
            pending.pop(0)
            if leftover >= 0.25:
                pending.append((subj, replace(topic, hours=leftover)))
            else:
                # อ่านจบหัวข้อ -> เข้าคิวทบทวน
                sim[topic.code] = srs.first_schedule(cursor, intervals)

        days.append(sd)
        cursor += timedelta(days=1)

    return days


def plan_for_day(
    cfg: Dict[str, Any], store: ProgressStore, day: date
) -> StudyDay:
    """ตารางของวันเดียว — ใช้กับคำสั่ง `today` และการแจ้งเตือนรายวัน."""
    plan = generate_plan(cfg, store, start=day, end=day + timedelta(days=1))
    for sd in plan:
        if sd.day == day:
            return sd
    return StudyDay(day=day, note="ไม่มีตาราง")


def coverage(cfg: Dict[str, Any], store: ProgressStore) -> Dict[str, Dict[str, float]]:
    """สรุปความคืบหน้าต่อวิชา: อ่านไปกี่ % ของชั่วโมงทั้งหมด และความแม่นเฉลี่ย."""
    baseline = float(cfg.get("baseline_mastery", 35.0))
    out: Dict[str, Dict[str, float]] = {}
    for code, subj in syllabus.SUBJECTS.items():
        done = sum(t.hours for t in subj.topics if store.is_learned(t.code))
        total = subj.total_hours
        out[code] = {
            "name": subj.name,
            "hours_done": round(done, 1),
            "hours_total": round(total, 1),
            "pct": round(100.0 * done / total, 1) if total else 0.0,
            "topics_done": sum(1 for t in subj.topics if store.is_learned(t.code)),
            "topics_total": len(subj.topics),
            "mastery": round(store.subject_mastery(code, subj.topics, baseline), 1),
        }
    return out
