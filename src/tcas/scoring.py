"""คำนวณคะแนนรวม กสพท จากคะแนนดิบ + ตรวจเกณฑ์ขั้นต่ำ.

สูตร (ตามค่าใน config/tcas_config.yaml)

    คะแนนรวม 100 = TPAT1 30% + A-Level 70%

    ภายใน A-Level 70%:  วิทย์ 40 · คณิต1 20 · อังกฤษ 20 · ไทย 10 · สังคม 10
    (วิทย์ = ค่าเฉลี่ยของ ฟิสิกส์ เคมี ชีววิทยา น้ำหนักเท่ากัน)

เกณฑ์ขั้นต่ำ: ต่ำกว่าเกณฑ์แม้ข้อเดียว = ตกทันที ไม่ว่าคะแนนรวมจะสูงแค่ไหน

⚠️ ตัวเลขทั้งหมดอ่านจาก config — ต้องยืนยันกับประกาศ กสพท ปีการศึกษา 2570
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import syllabus
from .models import ScoreCard

# ชื่อกลุ่มที่ใช้แสดงผล
GROUP_LABELS = {
    "tpat1": "TPAT1 วิชาเฉพาะ กสพท",
    "science": "วิทยาศาสตร์ (ฟิสิกส์+เคมี+ชีวะ)",
    "math1": "คณิตศาสตร์ประยุกต์ 1",
    "english": "ภาษาอังกฤษ",
    "thai": "ภาษาไทย",
    "social": "สังคมศึกษา",
}


def group_weights(cfg: Dict[str, Any]) -> Dict[str, float]:
    """น้ำหนักของแต่ละกลุ่มเทียบคะแนนเต็ม 100."""
    k = cfg.get("kaspot") or {}
    tpat1_w = float(k.get("tpat1_weight", 30.0))
    alevel_w = float(k.get("alevel_weight", 70.0))
    split = k.get("alevel_split") or {}
    weights = {"tpat1": tpat1_w}
    for group, share in split.items():
        weights[group] = alevel_w * float(share) / 100.0
    return weights


def to_percent(subject_code: str, raw: float) -> float:
    """แปลงคะแนนดิบเป็น % ของคะแนนเต็มวิชานั้น (TPAT1 เต็ม 300, A-Level เต็ม 100)."""
    subj = syllabus.get_subject(subject_code)
    return 100.0 * float(raw) / subj.max_score if subj.max_score else 0.0


def group_percents(raw_scores: Dict[str, float]) -> Dict[str, float]:
    """รวมคะแนนดิบรายวิชาเป็น % รายกลุ่ม (วิทย์เฉลี่ย 3 วิชา)."""
    per_group: Dict[str, List[float]] = {}
    for code, raw in raw_scores.items():
        if code not in syllabus.SUBJECTS:
            continue
        group = syllabus.get_subject(code).group
        per_group.setdefault(group, []).append(to_percent(code, raw))
    return {g: sum(vals) / len(vals) for g, vals in per_group.items() if vals}


def missing_subjects(raw_scores: Dict[str, float]) -> List[str]:
    """วิชาที่ยังไม่ได้กรอกคะแนน — คะแนนรวมจะยังไม่สมบูรณ์."""
    return [c for c in syllabus.SUBJECTS if c not in raw_scores]


def compute(cfg: Dict[str, Any], raw_scores: Dict[str, float]) -> ScoreCard:
    """คำนวณคะแนนรวม กสพท จากคะแนนดิบที่มี.

    วิชาที่ยังไม่กรอกจะถูกนับเป็น 0 ในคะแนนรวม และรายงานไว้ใน `missing`
    """
    weights = group_weights(cfg)
    pcts = group_percents(raw_scores)
    mins = (cfg.get("kaspot") or {}).get("minimums") or {}

    total = 0.0
    breakdown: Dict[str, tuple] = {}
    for group, weight in weights.items():
        pct = pcts.get(group, 0.0)
        weighted = weight * pct / 100.0
        total += weighted
        breakdown[group] = (round(pct, 2), round(weighted, 2))

    # ---------------------------------------------------- เกณฑ์ขั้นต่ำ
    failures: List[str] = []
    missing = missing_subjects(raw_scores)

    tpat1_min = float(mins.get("tpat1_pct", 30.0))
    if "tpat1" in pcts and pcts["tpat1"] < tpat1_min:
        failures.append(
            f"TPAT1 ได้ {pcts['tpat1']:.1f}% ต่ำกว่าเกณฑ์ {tpat1_min:.0f}%"
        )

    each_min = float(mins.get("alevel_each_group_pct", 30.0))
    eng_min = float(mins.get("english_pct", each_min))
    for group, pct in pcts.items():
        if group == "tpat1":
            continue
        floor = eng_min if group == "english" else each_min
        if pct < floor:
            failures.append(
                f"{GROUP_LABELS.get(group, group)} ได้ {pct:.1f}% ต่ำกว่าเกณฑ์ {floor:.0f}%"
            )

    return ScoreCard(
        total=round(total, 2),
        breakdown=breakdown,
        passed_minimums=not failures,
        failures=failures,
        missing=missing,
    )


def required_percent(
    cfg: Dict[str, Any],
    raw_scores: Dict[str, float],
    target_total: float,
) -> Optional[float]:
    """ต้องทำ % เท่าไรในวิชาที่ยังไม่ได้กรอก จึงจะไปถึงคะแนนรวมเป้าหมาย.

    สมมติว่าทุกวิชาที่เหลือทำได้ % เท่ากันหมด
    คืน None ถ้ากรอกครบแล้ว, คืน >100 ถ้าเป็นไปไม่ได้แล้ว (ผู้เรียกควรเตือน)
    """
    weights = group_weights(cfg)
    pcts = group_percents(raw_scores)
    missing = missing_subjects(raw_scores)
    if not missing:
        return None

    have = sum(weights.get(g, 0.0) * p / 100.0 for g, p in pcts.items())

    # น้ำหนักที่ยังว่างอยู่ — กลุ่มวิทย์คิดตามสัดส่วนวิชาที่ยังขาดในกลุ่ม
    open_weight = 0.0
    for group, weight in weights.items():
        subject_codes = syllabus.GROUPS.get(group, [])
        if not subject_codes:
            continue
        n_missing = sum(1 for c in subject_codes if c in missing)
        open_weight += weight * n_missing / len(subject_codes)

    if open_weight <= 0:
        return None
    return round(100.0 * (target_total - have) / open_weight, 1)


def project_from_mastery(cfg: Dict[str, Any], store, floor: float = 0.0) -> Dict[str, float]:
    """ประมาณคะแนนดิบของทุกวิชาจาก 'ความแม่น' ที่สะสมจากการทำ quiz.

    ใช้ตอนที่ยังไม่มีคะแนนสอบจริง เพื่อดูว่า ณ วันนี้ยืนอยู่ตรงไหน
    เป็นการประมาณหยาบ ๆ — ความแม่นจาก quiz ในบ้านมักสูงกว่าคะแนนสอบจริง
    """
    baseline = float(cfg.get("baseline_mastery", 35.0))
    out: Dict[str, float] = {}
    for code, subj in syllabus.SUBJECTS.items():
        mastery = store.subject_mastery(code, subj.topics, baseline)
        out[code] = round(max(floor, mastery) * subj.max_score / 100.0, 1)
    return out
