#!/usr/bin/env python3
"""ตรวจคลังข้อสอบให้ครบกว่าที่ `tcas_cli.py bank` ตรวจ

รันก่อน commit ทุกครั้งที่แตะ data/tcas/questions/
    python3 tools/check_bank.py

ที่มา: ชุดข้อสอบ 121 ข้อที่เพิ่มเมื่อ 2026-09-03 มีเฉลยกองอยู่ที่ช่อง B ถึง 62%
(เดาได้โดยไม่ต้องอ่านโจทย์) ทั้งที่ docs เตือนเรื่องนี้ไว้แล้ว — เพราะไม่มี
สคริปต์ที่รันได้จริง คำเตือนที่เป็นข้อความเฉย ๆ จึงถูกข้าม ไฟล์นี้แก้ตรงนั้น
"""
from __future__ import annotations

import collections
import pathlib
import re
import sys

import yaml

QDIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "tcas" / "questions"
MIN_PER_TOPIC = 5
SKEW_LIMIT = 0.35   # ไม่มีช่องไหนควรเกิน 35% ของเฉลยทั้งหมด (สุ่มเท่ากันคือ 25%)


def load() -> list[tuple[str, dict]]:
    out = []
    for f in sorted(QDIR.glob("*.yaml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        for q in doc.get("questions", []):
            out.append((f.name, q))
    return out


def main() -> int:
    items = load()
    bad: list[str] = []
    qids: collections.Counter = collections.Counter()
    stems: dict[str, list[str]] = collections.defaultdict(list)
    topics: collections.Counter = collections.Counter()

    for fname, q in items:
        qid = q.get("qid", "?")
        qids[qid] += 1
        stems[" ".join(str(q.get("stem", "")).split())].append(qid)
        topics[q.get("topic", "?")] += 1

        ch = q.get("choices") or []
        if len(ch) < 4:
            bad.append(f"{qid}: มีตัวเลือกแค่ {len(ch)}")
        if not isinstance(q.get("answer"), int) or not 0 <= q["answer"] < len(ch):
            bad.append(f"{qid}: answer={q.get('answer')} อยู่นอกช่วง")
        # เทียบแบบ *สนตัวพิมพ์ใหญ่-เล็ก* — มีข้อที่ถามเรื่องตัวพิมพ์เอง
        # (bio_diversity_003 ถามการเขียนชื่อวิทยาศาสตร์)
        norm = [" ".join(str(c).split()) for c in ch]
        if len(set(norm)) != len(norm):
            bad.append(f"{qid}: ตัวเลือกซ้ำกัน")
        if not str(q.get("explanation", "")).strip():
            bad.append(f"{qid}: ไม่มีคำอธิบาย")
        if q.get("difficulty") not in (1, 2, 3):
            bad.append(f"{qid}: difficulty={q.get('difficulty')}")
        # คำอธิบายห้ามอ้างตัวเลือกด้วยเลขลำดับ — พอสลับตำแหน่งเฉลยแล้วจะชี้ผิดข้อ
        if re.search(r"ตัวเลือก\s*[0-9]", str(q.get("explanation", ""))):
            bad.append(f"{qid}: คำอธิบายอ้าง 'ตัวเลือก N' ให้อ้างข้อความแทน")

    for qid, n in qids.items():
        if n > 1:
            bad.append(f"qid ซ้ำ {n} ครั้ง: {qid}")
    for stem, ids in stems.items():
        if len(ids) > 1:
            bad.append(f"โจทย์ซ้ำ: {' / '.join(ids)} — «{stem[:50]}»")
    for t, n in sorted(topics.items()):
        if n < MIN_PER_TOPIC:
            bad.append(f"หัวข้อ {t} มีแค่ {n} ข้อ (ขั้นต่ำ {MIN_PER_TOPIC})")

    # ── การกระจายตำแหน่งเฉลย ──────────────────────────────────
    slots = collections.Counter(q["answer"] for _, q in items
                                if isinstance(q.get("answer"), int))
    total = sum(slots.values())
    line = "  ".join(f"{'ABCDE'[k]}={slots[k]:4} ({100*slots[k]/total:4.1f}%)"
                     for k in sorted(slots))
    print(f"คลัง {len(items)} ข้อ · {len(topics)} หัวข้อ")
    print(f"ตำแหน่งเฉลย: {line}")
    for k, n in slots.items():
        if n / total > SKEW_LIMIT:
            bad.append(f"เฉลยกองที่ช่อง {'ABCDE'[k]} {100*n/total:.1f}% "
                       f"(เกิน {SKEW_LIMIT:.0%}) — เดาได้โดยไม่ต้องอ่านโจทย์")

    if bad:
        print(f"\n❌ พบปัญหา {len(bad)} ข้อ")
        for b in bad:
            print("  -", b)
        return 1
    print("\n✅ ผ่านทุกข้อ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
