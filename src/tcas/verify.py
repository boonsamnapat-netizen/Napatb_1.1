"""ตรวจสอบว่าตัวเลขไหนในระบบยังเป็นค่าประมาณ และต้องไปดูที่ไหน

แอปนี้เอาไว้ช่วยตัดสินใจเรื่องอนาคตของคน ตัวเลขที่ผิดจึงแพงกว่าบั๊กทั่วไปมาก
โมดูลนี้จึงรวบรวม "ทุกค่าที่ยังไม่ได้ยืนยัน" ไว้ที่เดียว พร้อมบอกว่าต้องเปิด
หน้าไหนไปเทียบ และแก้บรรทัดไหนของไฟล์ไหน

ตั้งใจให้เป็นรายการที่ไล่เช็คจนหมดได้จริงในหนึ่งนั่ง ไม่ใช่คำเตือนลอย ๆ
ท้ายหน้าเว็บที่อ่านแล้วก็ไม่รู้ว่าจะเริ่มตรงไหน
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List

from .config import load_config, load_programs, load_resources

# แหล่งอ้างอิงจริงของแต่ละชนิดข้อมูล — เขียนไว้ที่เดียว จะได้ไม่กระจาย
SOURCES = {
    "exam": "https://www.mytcas.com  (ปฏิทินการสมัครสอบและปฏิทินการสอบ TCAS70)",
    "milestone": "https://www.mytcas.com  (ปฏิทินการรับสมัคร)",
    "weights": "ประกาศ กสพท ฉบับที่ 1 — หลักเกณฑ์การคัดเลือก ข้อ 4 (https://cotmesadmission.com)",
    "minimum": "ประกาศ กสพท ฉบับที่ 1 ข้อ 4 ช่องเงื่อนไข (https://cotmesadmission.com)",
    "cutoff": "ประกาศผลคะแนนต่ำสุด กสพท ย้อนหลัง (กสพท เผยแพร่หลังประกาศผลแต่ละปี)",
    "resource": "เปิดลิงก์แล้วดูว่ายังใช้ได้และเนื้อหาตรงกับวิชานั้นจริง",
}

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@dataclass
class Finding:
    """หนึ่งค่าที่ยังไม่ยืนยัน"""

    severity: str          # critical / high / medium / low
    kind: str              # คีย์ใน SOURCES
    where: str             # ไฟล์ + path ที่ต้องแก้
    what: str              # ค่าปัจจุบันที่ยังไม่ยืนยัน
    why: str               # ถ้าผิดแล้วเกิดอะไรขึ้น

    @property
    def source(self) -> str:
        return SOURCES.get(self.kind, "")


@dataclass
class Audit:
    findings: List[Finding] = field(default_factory=list)
    verified: int = 0

    @property
    def total(self) -> int:
        return len(self.findings) + self.verified

    def by_severity(self) -> List[Finding]:
        return sorted(self.findings, key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.where))

    def counts(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for f in self.findings:
            out[f.severity] = out.get(f.severity, 0) + 1
        return out


def _unverified(spec: Any) -> bool:
    return not bool((spec or {}).get("verified", False))


def _stale(spec: Any, target_year: int | None) -> bool:
    """ยืนยันแล้วจริง แต่เอกสารที่ใช้ยืนยันเป็นของปีอื่น.

    เกณฑ์ กสพท นิ่งมาหลายปี แต่ กสพท มีสิทธิ์เปลี่ยนทุกปี การบอกว่า
    "ยืนยันแล้ว" เฉย ๆ จึงยังไม่พอ — ต้องบอกด้วยว่ายืนยันกับประกาศปีไหน
    """
    year = (spec or {}).get("source_year")
    return bool(target_year and year and int(year) != int(target_year))


def _stale_note(spec: Any) -> str:
    return (f' — ยืนยันกับประกาศปี {spec.get("source_year")} '
            f'({spec.get("source", "ไม่ได้ระบุแหล่ง")})')


def audit(
    cfg: Dict[str, Any] | None = None,
    programs: Dict[str, Any] | None = None,
    resources: Dict[str, Any] | None = None,
) -> Audit:
    cfg = cfg if cfg is not None else load_config()
    programs = programs if programs is not None else load_programs()
    resources = resources if resources is not None else load_resources()

    a = Audit()
    target_year = cfg.get("target_year")

    # ── วันสอบ ──────────────────────────────────────────────────
    # ผิดแล้วเสียหายที่สุด เพราะทั้งตารางอ่านย้อนกลับมาจากวันสอบ
    for key, spec in (cfg.get("exams") or {}).items():
        target = f"config/tcas_config.yaml → exams.{key}.date"
        value = f'{spec.get("name", key)} = {spec.get("date")}'
        if _unverified(spec):
            a.findings.append(Finding(
                severity="critical", kind="exam", where=target, what=value,
                why="ตารางอ่านทั้งหมดนับถอยหลังจากวันนี้ — เลื่อนไปหนึ่งเดือน แผนทั้งปีผิดหมด",
            ))
        elif _stale(spec, target_year):
            a.findings.append(Finding(
                severity="medium", kind="exam", where=target,
                what=value + _stale_note(spec),
                why="วันสอบของปีที่แล้วไม่ใช่วันสอบของปีนี้ ต้องเทียบกับปฏิทินปีปัจจุบัน",
            ))
        else:
            a.verified += 1

    # ── หมุดหมายการรับสมัคร ────────────────────────────────────
    for m in cfg.get("milestones") or []:
        target = "config/tcas_config.yaml → milestones"
        value = f'{m.get("label")} = {m.get("date")}'
        if _unverified(m):
            a.findings.append(Finding(
                severity="high", kind="milestone", where=target, what=value,
                why="พลาดวันสมัครคือจบเกม ไม่มีรอบแก้ตัว",
            ))
        else:
            a.verified += 1

    # ── สัดส่วนคะแนนและเกณฑ์ขั้นต่ำ ────────────────────────────
    k = cfg.get("kaspot") or {}
    split = k.get("alevel_split") or {}
    weights_value = (f'TPAT1 {k.get("tpat1_weight")}% + A-Level {k.get("alevel_weight")}% '
                     f'(วิทย์ {split.get("science")} · คณิต {split.get("math1")} · '
                     f'อังกฤษ {split.get("english")} · ไทย {split.get("thai")} · '
                     f'สังคม {split.get("social")})')
    if _unverified(k):
        a.findings.append(Finding(
            severity="critical", kind="weights",
            where="config/tcas_config.yaml → kaspot.tpat1_weight / alevel_weight / alevel_split",
            what=weights_value,
            why="สัดส่วนนี้กำหนดว่าควรทุ่มเวลาให้วิชาไหน — ผิดแล้วอ่านผิดวิชาทั้งปี",
        ))
    elif _stale(k, target_year):
        a.findings.append(Finding(
            severity="medium", kind="weights",
            where="config/tcas_config.yaml → kaspot",
            what=weights_value + _stale_note(k),
            why="กสพท เปลี่ยนสัดส่วนได้ทุกปี — ต้องเทียบกับประกาศฉบับที่ 1 ของปีนี้",
        ))
    else:
        a.verified += 1

    mins = k.get("minimums") or {}
    # ตัดคีย์กำกับออก มันเป็นธง ไม่ใช่ค่าที่ต้องไปเทียบกับประกาศ
    mins_value = ", ".join(
        f"{key} = {'ไม่มีเกณฑ์' if val is None else val}"
        for key, val in mins.items()
        if key not in ("verified", "source", "source_year"))
    if mins and _unverified(mins):
        a.findings.append(Finding(
            severity="high", kind="minimum",
            where="config/tcas_config.yaml → kaspot.minimums",
            what=mins_value,
            why="ตกเกณฑ์ขั้นต่ำคือคัดออกทันที ต่อให้คะแนนรวมสูงแค่ไหน",
        ))
    elif mins and _stale(mins, target_year):
        a.findings.append(Finding(
            severity="medium", kind="minimum",
            where="config/tcas_config.yaml → kaspot.minimums",
            what=mins_value + _stale_note(mins),
            why="ตกเกณฑ์ขั้นต่ำคือคัดออกทันที — เกณฑ์ปีที่แล้วอาจไม่ใช่ของปีนี้",
        ))
    elif mins:
        a.verified += 1

    # ── คะแนนต่ำสุดของแต่ละคณะ ─────────────────────────────────
    for p in programs.get("programs") or []:
        if _unverified(p):
            a.findings.append(Finding(
                severity="high", kind="cutoff",
                where=f'config/tcas_programs.yaml → programs[{p.get("code")}].cutoffs',
                what=f'{p.get("name")} = {p.get("cutoffs")}',
                why="เป็นตัวเลขที่ผู้ใช้เอาไปตัดสินใจว่าจะยื่นคณะไหน",
            ))
        else:
            a.verified += 1

    # ── ลิงก์แหล่งเรียนรู้ ──────────────────────────────────────
    for h in resources.get("hubs") or []:
        if _unverified(h):
            a.findings.append(Finding(
                severity="low", kind="resource",
                where="config/tcas_resources.yaml → hubs",
                what=f'{h.get("name")} — {h.get("url")}',
                why="ลิงก์เสียแค่ทำให้เสียเวลา ไม่ได้ทำให้ตัดสินใจผิด",
            ))
        else:
            a.verified += 1

    return a


def render(a: Audit) -> str:
    """รายงานแบบอ่านในเทอร์มินัล"""
    lines: List[str] = []
    counts = a.counts()
    done = a.verified
    total = a.total

    lines.append("🔍 ตรวจความน่าเชื่อถือของข้อมูล")
    lines.append("")
    if not a.findings:
        lines.append(f"✅ ยืนยันครบทั้ง {total} รายการแล้ว")
        return "\n".join(lines)

    bar_done = int(round(20 * done / total)) if total else 0
    lines.append(f"ยืนยันแล้ว {done}/{total}  [{'█' * bar_done}{'░' * (20 - bar_done)}]")
    order = ["critical", "high", "medium", "low"]
    label = {"critical": "ห้ามปล่อยผ่าน", "high": "สำคัญ", "medium": "ควรตรวจ", "low": "เล็กน้อย"}
    lines.append("  " + " · ".join(
        f"{label[s]} {counts[s]}" for s in order if counts.get(s)))
    lines.append("")

    current = None
    for f in a.by_severity():
        if f.severity != current:
            current = f.severity
            lines.append(f"── {label[f.severity]} ──────────────────────────────")
            lines.append(f"   ดูจาก: {f.source}")
            lines.append("")
        lines.append(f"  • {f.what}")
        lines.append(f"    แก้ที่ {f.where}")
        lines.append(f"    ถ้าผิด: {f.why}")
        lines.append("")

    lines.append("เมื่อตรวจแล้ว ให้ตั้ง verified: true ในรายการนั้น")
    lines.append("แล้วรันคำสั่งนี้ซ้ำจนกว่าจะไม่เหลือระดับ 'ห้ามปล่อยผ่าน'")
    return "\n".join(lines)


def summary_for_web(a: Audit) -> Dict[str, Any]:
    """ข้อมูลย่อสำหรับแสดงในแอป — ผู้ใช้ปลายทางควรเห็นว่าอะไรยังไม่ยืนยัน"""
    return {
        "total": a.total,
        "verified": a.verified,
        "counts": a.counts(),
        "items": [
            {"severity": f.severity, "kind": f.kind, "what": f.what}
            for f in a.by_severity()
        ],
        "generatedAt": date.today().isoformat(),
    }
