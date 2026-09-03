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
import difflib
import itertools
import pathlib
import re
import sys

import yaml

QDIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "tcas" / "questions"
MIN_PER_TOPIC = 5
SKEW_LIMIT = 0.35   # ไม่มีช่องไหนควรเกิน 35% ของเฉลยทั้งหมด (สุ่มเท่ากันคือ 25%)

# เพดาน "เฉลยเป็นตัวเลือกที่ยาวที่สุด" รายวิชา — ตั้งไว้ที่ค่าปัจจุบันเพื่อกันถอยหลัง
# ยังห่างจากเป้าหมาย 25% อยู่มาก ต้องไล่เขียนตัวลวงให้ยาวพอ ๆ กับเฉลยทีละวิชา
# (จริยธรรม TPAT1 ทำไปแล้ว 46 ข้อ จาก 76% เหลือ 26%)
LONGEST_CAP = {
    "bio": 65.8, "chem": 67.1, "eng": 52.4, "math1": 44.6,
    "phys": 62.5, "social": 81.9, "thai": 74.6, "tpat1": 53.4,
}


# คู่ที่หน้าตาคล้ายกันแต่ "ไม่ใช่" ข้อซ้ำ — คนละโจทย์ที่บังเอิญเฉลยเป็นค่าเดียวกัน
# ใส่ไว้ตรงนี้เท่านั้น อย่าไปลดเกณฑ์ความคล้ายเพื่อให้มันรอด
NOT_DUPES = {
    ("math_trig_001", "math_trig_003"),      # sin30+cos60 กับ tan45 ต่างโจทย์ แต่ตอบ 1 เท่ากัน
    ("tpat1_series_005", "tpat1_series_006"),  # กำลังสอง กับ คูณเพิ่ม คนละแบบ
}


def _sim(a, b) -> float:
    """ความคล้ายของข้อความ โดยตัดเว้นวรรคและเครื่องหมายออกก่อน."""
    norm = lambda s: re.sub(r"[^\w฀-๿]", "", re.sub(r"\s+", "", str(s))).lower()
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def load() -> list[tuple[str, dict]]:
    out = []
    for f in sorted(QDIR.glob("*.yaml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        subject = doc.get("subject")
        for q in doc.get("questions", []):
            # วิชาอยู่ที่หัวไฟล์ ไม่ได้อยู่ในแต่ละข้อ — ติดไปกับข้อเลยจะได้จัดกลุ่มง่าย
            q.setdefault("subject", subject)
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

    # ── ข้อที่ถามเรื่องเดียวกันซ้ำ ─────────────────────────────
    # โจทย์ที่พิมพ์ต่างกันนิดหน่อยแต่ถามเรื่องเดียวกันและเฉลยตรงกัน = ข้อซ้ำ
    # ตัวตรวจ "โจทย์ตรงกันเป๊ะ" จับไม่ได้ เพราะแค่เว้นวรรคต่างก็รอดแล้ว
    # ข้อซ้ำไม่ใช่แค่เปลืองที่ — มันดันค่าความแม่นของหัวข้อให้สูงเกินจริง
    by_topic: dict[str, list] = {}
    for _f, q in items:
        by_topic.setdefault(q.get("topic"), []).append(q)
    for topic, qs in sorted(by_topic.items()):
        for qa, qb in itertools.combinations(qs, 2):
            pair = tuple(sorted((qa["qid"], qb["qid"])))
            if pair in NOT_DUPES:
                continue
            if _sim(qa["stem"], qb["stem"]) < 0.70:
                continue
            try:
                aa, ab = qa["choices"][qa["answer"]], qb["choices"][qb["answer"]]
            except (IndexError, TypeError, KeyError):
                continue
            if _sim(aa, ab) >= 0.80:
                bad.append(f"ถามซ้ำกันในหัวข้อ {topic}: {pair[0]} กับ {pair[1]}")

    # ── เฉลยยาวกว่าตัวลวงจนเดาได้ ─────────────────────────────
    # ถ้าเฉลยเป็นตัวเลือกที่ยาวที่สุดบ่อยเกินไป เด็กจะทำคะแนนได้โดยไม่ต้องอ่านโจทย์
    # (คนเขียนข้อสอบมักใส่เหตุผลประกอบไว้ในข้อถูก แต่เขียนตัวลวงห้วน ๆ)
    # สุ่มล้วน = 25% · เป้าหมายคือไล่ลดให้เข้าใกล้ค่านั้น
    #
    # ตัวเลขข้างล่างคือ "เพดานปัจจุบัน" ไม่ใช่ค่าที่ยอมรับได้ — ห้ามขยับขึ้น
    # แก้ข้อไหนให้ตัวลวงยาวขึ้นแล้ว ให้ลดเพดานของวิชานั้นลงตามจริง
    by_subject: dict[str, list] = {}
    for _f, q in items:
        by_subject.setdefault(q.get("subject") or "?", []).append(q)
    print("\nเฉลยเป็นตัวเลือกที่ยาวที่สุด (สุ่มล้วน = 25%):")
    for subj, qs in sorted(by_subject.items()):
        longest = sum(1 for q in qs
                      if isinstance(q.get("choices"), list) and q["choices"]
                      and len(str(q["choices"][q["answer"]]))
                      == max(len(str(c)) for c in q["choices"]))
        pct = 100.0 * longest / len(qs)
        cap = LONGEST_CAP.get(subj)
        mark = ""
        if cap is not None and pct > cap:
            mark = f"  ← เกินเพดาน {cap:.0f}%"
            bad.append(f"วิชา {subj}: เฉลยเป็นตัวเลือกยาวที่สุด {pct:.0f}% "
                       f"(เพดาน {cap:.0f}%) — เดาได้โดยไม่ต้องอ่านโจทย์")
        print(f"  {subj:8s} {len(qs):4d} ข้อ  {pct:5.1f}%{mark}")

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
