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
        }
    return dict(sorted(out.items(), key=lambda kv: kv[1]["date"]))


def next_exam(cfg: Dict[str, Any], ref: date | None = None) -> Dict[str, Any] | None:
    """สนามสอบถัดไปที่ยังไม่ผ่าน."""
    ref = ref or today()
    for spec in exam_dates(cfg).values():
        if spec["date"] >= ref:
            return spec
    return None
