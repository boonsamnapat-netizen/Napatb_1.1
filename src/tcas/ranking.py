"""จัดอันดับคณะและประเมินโอกาสติด เทียบคะแนนที่คาดว่าจะได้กับคะแนนต่ำสุดย้อนหลัง.

วิธีประเมิน
  1. หาแนวโน้ม (trend) ของคะแนนต่ำสุดจากปีที่มีข้อมูล — เฉลี่ยส่วนต่างต่อปี
  2. คาดคะแนนต่ำสุดปีเป้าหมาย = ค่าล่าสุด + trend
  3. margin = คะแนนเรา − คะแนนต่ำสุดที่คาด แล้วแปลงเป็นแถบโอกาส

⚠️ ความแม่นของผลลัพธ์ขึ้นกับความถูกต้องของ `cutoffs` ใน config/tcas_programs.yaml
   ซึ่งตั้งต้นเป็นค่าประมาณ (verified: false) — ต้องแทนที่ด้วยประกาศจริงก่อนใช้จริง
   คณะที่ยัง verified: false จะถูกทำเครื่องหมาย ⚠️ ในรายงานเสมอ
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .models import ProgramChance

# ขอบเขตของแต่ละแถบ (หน่วย = คะแนนรวม กสพท เต็ม 100)
BAND_SAFE = 3.0        # เกินคะแนนต่ำสุดที่คาดตั้งแต่ +3 ขึ้นไป
BAND_LIKELY = 0.0      # 0 ถึง +3
BAND_REACH = -3.0      # −3 ถึง 0

# ป้ายต้องตรงกับ BANDS ใน web/tcas_app.html เป๊ะ ๆ — ถ้า CLI กับแอปเรียกคนละชื่อ
# ผู้ใช้จะไม่รู้ว่าอันไหนจริง (ยึดคำของแอป เพราะเป็นสิ่งที่เห็นทุกวัน)
BAND_SAFE_LABEL = "ค่อนข้างปลอดภัย"
BAND_LIKELY_LABEL = "ลุ้นได้"
BAND_REACH_LABEL = "ท้าทาย"
BAND_FAR_LABEL = "ยังห่าง"
BAND_NODATA_LABEL = "ไม่มีข้อมูล"

BAND_ORDER = [
    BAND_SAFE_LABEL,
    BAND_LIKELY_LABEL,
    BAND_REACH_LABEL,
    BAND_FAR_LABEL,
    BAND_NODATA_LABEL,
]


def _trend(cutoffs: Dict[int, float]) -> float:
    """ส่วนต่างเฉลี่ยของคะแนนต่ำสุดต่อปี (บวก = คะแนนต่ำสุดขยับสูงขึ้น)."""
    years = sorted(cutoffs)
    if len(years) < 2:
        return 0.0
    deltas = [
        (cutoffs[b] - cutoffs[a]) / (b - a)
        for a, b in zip(years, years[1:])
        if b != a
    ]
    return sum(deltas) / len(deltas) if deltas else 0.0


def _band(margin: Optional[float]) -> str:
    if margin is None:
        return BAND_NODATA_LABEL
    if margin >= BAND_SAFE:
        return BAND_SAFE_LABEL
    if margin >= BAND_LIKELY:
        return BAND_LIKELY_LABEL
    if margin >= BAND_REACH:
        return BAND_REACH_LABEL
    return BAND_FAR_LABEL


def rank(
    programs_doc: Dict[str, Any],
    my_score: Optional[float],
    target_year: Optional[int] = None,
    faculty: Optional[str] = None,
    university: Optional[str] = None,
) -> List[ProgramChance]:
    """จัดอันดับคณะจากคะแนนต่ำสุดที่คาด (สูงไปต่ำ) พร้อมประเมินโอกาส.

    `faculty` และ `university` เป็นตัวกรองคนละแกน — "อยากเข้าทันตะ" กับ
    "อยากอยู่ ม.ธรรมศาสตร์" เป็นคำถามคนละคำถาม ใส่พร้อมกันได้
    ทั้งคู่เทียบแบบ substring เพื่อให้พิมพ์ "ธรรมศาสตร์" แทน "ม.ธรรมศาสตร์" ได้
    """
    meta = programs_doc.get("meta") or {}
    years = meta.get("years") or []
    if target_year is None:
        target_year = max(years) if years else None

    out: List[ProgramChance] = []
    for spec in programs_doc.get("programs") or []:
        if faculty and faculty not in str(spec.get("faculty") or ""):
            continue
        if university and university not in str(spec.get("university") or ""):
            continue

        cutoffs = {int(k): float(v) for k, v in (spec.get("cutoffs") or {}).items()}
        latest_year = max(cutoffs) if cutoffs else None
        latest = cutoffs[latest_year] if latest_year else None
        trend = _trend(cutoffs)

        projected = None
        if latest is not None:
            gap = (target_year - latest_year) if (target_year and latest_year) else 1
            projected = round(latest + trend * max(gap, 0), 2)

        margin = (
            round(my_score - projected, 2)
            if (my_score is not None and projected is not None)
            else None
        )

        out.append(
            ProgramChance(
                code=str(spec.get("code", "")),
                name=str(spec.get("name", "")),
                faculty=str(spec.get("faculty", "")),
                university=str(spec.get("university", "")),
                seats=spec.get("seats"),
                latest_cutoff=latest,
                trend=round(trend, 2),
                projected_cutoff=projected,
                margin=margin,
                band=_band(margin),
                verified=bool(spec.get("verified", False)),
            )
        )

    # เรียงจากคณะที่คะแนนต่ำสุดสูงสุดลงมา — คณะไม่มีข้อมูลไปอยู่ท้ายสุด
    out.sort(
        key=lambda p: (p.projected_cutoff is None, -(p.projected_cutoff or 0.0))
    )
    return out


def shortlist(
    chances: List[ProgramChance],
    per_band: int = 3,
) -> Dict[str, List[ProgramChance]]:
    """จัดกลุ่มเป็น ปลอดภัย/ลุ้น/ท้าทาย เพื่อใช้วางอันดับ 1-10 ในรอบ 3.

    กลยุทธ์ที่ใช้กันคือใส่ 'ท้าทาย' ไว้อันดับต้น ตามด้วย 'ลุ้น' และปิดท้ายด้วย
    'ปลอดภัย' เพราะระบบ TCAS จัดให้ตามลำดับที่เลือก — ใส่คณะที่อยากได้จริงไว้บนสุด
    """
    grouped: Dict[str, List[ProgramChance]] = {b: [] for b in BAND_ORDER}
    for c in chances:
        grouped[c.band].append(c)
    return {b: grouped[b][:per_band] for b in BAND_ORDER if grouped[b]}


def suggested_order(chances: List[ProgramChance], limit: int = 10) -> List[ProgramChance]:
    """เสนอลำดับการเลือกอันดับในรอบ 3: ท้าทาย → ลุ้น → ปลอดภัย."""
    priority = {
        BAND_REACH_LABEL: 0,
        BAND_LIKELY_LABEL: 1,
        BAND_SAFE_LABEL: 2,
        BAND_FAR_LABEL: 3,
        BAND_NODATA_LABEL: 4,
    }
    ordered = sorted(
        chances,
        key=lambda c: (priority.get(c.band, 9), -(c.projected_cutoff or 0.0)),
    )
    return ordered[:limit]
