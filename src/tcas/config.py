"""โหลด config ของระบบ TCAS70."""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "config" / "tcas_config.yaml"
DEFAULT_PROGRAMS = REPO_ROOT / "config" / "tcas_programs.yaml"
DEFAULT_RESOURCES = REPO_ROOT / "config" / "tcas_resources.yaml"


def load_config(path: str | Path | None = None) -> Dict[str, Any]:
    p = Path(path) if path else DEFAULT_CONFIG
    if not p.is_absolute():
        p = REPO_ROOT / p
    if not p.exists():
        raise FileNotFoundError(f"ไม่พบไฟล์ config: {p}")
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_programs(path: str | Path | None = None) -> Dict[str, Any]:
    p = Path(path) if path else DEFAULT_PROGRAMS
    if not p.is_absolute():
        p = REPO_ROOT / p
    if not p.exists():
        raise FileNotFoundError(f"ไม่พบไฟล์คณะ: {p}")
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_resources(path: str | Path | None = None) -> Dict[str, Any]:
    """แหล่งเรียนรู้ — ไม่มีไฟล์ก็ไม่เป็นไร แอปจะเหลือแค่ปุ่มค้นหา"""
    p = Path(path) if path else DEFAULT_RESOURCES
    if not p.is_absolute():
        p = REPO_ROOT / p
    if not p.exists():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def resolve_path(rel: str | Path) -> Path:
    """แปลง path ใน config ให้เป็น absolute เทียบกับ repo root."""
    p = Path(rel)
    return p if p.is_absolute() else REPO_ROOT / p


def parse_date(value: Any) -> date:
    """YAML อาจ parse วันที่ให้เป็น date อยู่แล้ว หรือยังเป็น str."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()


def today(override: str | None = None) -> date:
    """วันนี้ — override ได้ทั้งจากพารามิเตอร์และ env TCAS_TODAY (ใช้เทส)."""
    raw = override or os.environ.get("TCAS_TODAY")
    if raw:
        return parse_date(raw)
    return date.today()


def exam_dates(cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """คืน {key: {name, date, verified}} เรียงตามวันสอบ."""
    out = {}
    for key, spec in (cfg.get("exams") or {}).items():
        out[key] = {
            "name": spec.get("name", key),
            "date": parse_date(spec["date"]),
            "verified": bool(spec.get("verified", False)),
            # ค่าเริ่มต้น True เพื่อไม่ให้ config เก่าที่ไม่มีคีย์นี้เงียบหายไปจากการนับถอยหลัง
            "counts": bool(spec.get("counts_toward_kaspot", True)),
        }
    return dict(sorted(out.items(), key=lambda kv: kv[1]["date"]))


def subject_schedule(cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """ตารางสอบรายวิชา {code: {date, time}} — ว่างได้ถ้า config ไม่ได้ระบุ.

    A-Level กระจายอยู่หลายวัน การรู้ว่าวิชาไหนสอบวันไหนทำให้เส้นตายของ
    planner แม่นขึ้น และผู้ใช้เห็นได้ว่าต้องพร้อมอะไรก่อน
    """
    out: Dict[str, Dict[str, Any]] = {}
    for code, spec in (cfg.get("subject_schedule") or {}).items():
        if not spec or not spec.get("date"):
            continue
        out[code] = {"date": parse_date(spec["date"]), "time": spec.get("time")}
    return out


def next_exam(
    cfg: Dict[str, Any], ref: date | None = None, counting_only: bool = False
) -> Dict[str, Any] | None:
    """สนามสอบถัดไปที่ยังไม่ผ่าน.

    counting_only=True จะข้ามสนามที่ไม่มีน้ำหนักใน กสพท (เช่น TGAT) —
    ใช้กับตัวนับถอยหลังหลัก เพื่อไม่ให้เลขเด่นที่สุดบนหน้าจอชี้ผิดเป้า
    """
    ref = ref or today()
    for spec in exam_dates(cfg).values():
        if spec["date"] < ref:
            continue
        if counting_only and not spec.get("counts", True):
            continue
        return spec
    return None
