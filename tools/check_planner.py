#!/usr/bin/env python3
"""เทียบตารางอ่านฝั่ง Python (planner.py) กับฝั่ง JS (buildPlan ใน tcas_app.html)

สองฝั่งนี้ต้องให้ผลเหมือนกันทุกวัน ไม่งั้นนักเรียนที่ดูจากแอปกับจาก CLI
จะได้คำสั่งคนละอย่าง และไม่มีทางรู้ว่าอันไหนถูก

เทียบจาก "สถานะว่าง" ทั้งสองฝั่ง (ยังไม่เคยอ่าน ยังไม่เคยทำข้อสอบ)
— ถ้าจุดเริ่มต้นยังตรงกันไม่ได้ ที่เหลือไม่ต้องพูดถึง

วิธีรัน:
    python3 tcas_cli.py export
    python3 -m http.server -d web/dist 8765 &
    npm i playwright        # ครั้งแรกของ container
    python3 tools/check_planner.py [จำนวนวัน]
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.tcas import planner, quiz, syllabus  # noqa: E402
from src.tcas.config import load_config  # noqa: E402
from src.tcas.store import ProgressStore  # noqa: E402

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

_BANK = quiz.load_bank("data/tcas/questions")
QIDS_BY_TOPIC: dict = {}
for _qid, _q in _BANK.items():
    QIDS_BY_TOPIC.setdefault(_q.topic_code, []).append(_qid)
for _v in QIDS_BY_TOPIC.values():
    _v.sort()

JS = """
import { chromium } from 'playwright';
const B = await chromium.launch({ executablePath: process.env.PW_CHROME });
const ctx = await B.newContext();
const p = await ctx.newPage();
p.on('console', m => { if (m.type() === 'error') console.error('[console]', m.text()); });
const SEED = JSON.parse(process.env.PW_SEED);
await p.addInitScript(st => localStorage.setItem("tcas70.v1", JSON.stringify(st)), SEED);
await p.goto('http://localhost:8765/', {waitUntil:'networkidle'});
await p.waitForTimeout(200);
const out = await p.evaluate(a => buildPlan(a.from, a.n).map(x => ({
  date: x.date,
  blocks: x.blocks.map(b => [b.kind, b.topic, b.hours]),
})), {from: process.env.PW_FROM, n: Number(process.env.PW_N)});
console.log("@@" + JSON.stringify(out));
await B.close();
"""


BLANK = {"app": "tcas70", "seenIntro": True, "settings": {}, "scores": {},
         "topics": {}, "q": {}, "tests": {}, "days": {}, "links": {},
         "log": {}, "runs": [], "doneLegacy": {}, "venues": {}}


def js_plan(start: date, n: int, seed: dict) -> list:
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        f = pathlib.Path(td) / "plan.mjs"
        f.write_text(JS, encoding="utf-8")
        env = dict(os.environ, PW_CHROME=CHROME, PW_SEED=json.dumps(seed),
                   PW_FROM=start.isoformat(), PW_N=str(n))
        r = subprocess.run(["node", str(f)], capture_output=True, text=True,
                           cwd=ROOT, env=env)
    if r.returncode:
        raise SystemExit("รัน JS ไม่ได้:\n" + (r.stderr or r.stdout)[-2000:])
    line = next((l for l in r.stdout.splitlines() if l.startswith("@@")), None)
    if line is None:
        raise SystemExit("JS ไม่คืนผล:\n" + r.stdout[-1500:] + r.stderr[-1500:])
    return json.loads(line[2:])


def py_plan(start: date, n: int, seed: dict) -> list:
    """ชี้ไปไฟล์ที่ยังไม่มีจริง — ProgressStore จะเริ่มจากศูนย์ให้ แล้วค่อยยัด seed"""
    cfg = load_config()
    with tempfile.TemporaryDirectory() as td:
        st = ProgressStore(pathlib.Path(td) / "empty.json")
        st.data.update(seed)
        days = planner.generate_plan(cfg, st, start=start,
                                     end=start + timedelta(days=n - 1))
    return [
        {"date": d.day.isoformat(),
         "blocks": [[b.kind, b.topic_code, b.hours] for b in d.blocks]}
        for d in days
    ]


def dups(plan: list) -> list:
    out = []
    for d in plan:
        codes = [b[1] for b in d["blocks"]]
        if len(set(codes)) != len(codes):
            out.append(d["date"])
    return out


def scenarios(start: date) -> list:
    """สถานะทดสอบ — บรรยายครั้งเดียว แล้วแปลงเป็นรูปของแต่ละฝั่ง.

    สองฝั่งเก็บของหน้าตาต่างกัน (camelCase ในเบราว์เซอร์ · snake_case ใน JSON
    ของ CLI) แต่ต้อง "หมายถึงเรื่องเดียวกัน" ตรงนี้คือที่แปลงให้
    """
    ymd = lambda k: (start + timedelta(days=k)).isoformat()
    specs = [
        ("เริ่มจากศูนย์ (เพิ่งลงแอป)", {}),
        ("อ่านค้างไว้ครึ่งทาง + มีคิวทบทวน + เคยทำข้อสอบ", {
            "partial": {"tpat1_series": 3.0, "math_function": 1.5, "bio_cell": 0.75},
            "learned": {"tpat1_spatial": (-20, 2), "tpat1_logic": (-3, 0)},
            "quiz": {"tpat1_series": (10, 3), "bio_cell": (8, 7)},
            "today_log": [],
        }),
        ("อ่านไปแล้วครึ่งวันของวันนี้ (ตารางต้องเหลือแค่ส่วนที่ค้าง)", {
            "partial": {"tpat1_series": 3.0},
            "learned": {"tpat1_spatial": (-20, 2)},
            "quiz": {},
            "today_log": [("tpat1_series", 1.5), ("tpat1_logic", 1.5)],
        }),
    ]

    out = []
    for name, sp in specs:
        js = json.loads(json.dumps(BLANK))
        py = {"topics": {}, "questions": {}, "study_log": {}, "day_log": {}}

        for code, hrs in (sp.get("partial") or {}).items():
            js["topics"][code] = {"hoursDone": hrs}
            py["topics"][code] = {"hours_done": hrs}
        for code, (learned_off, rep) in (sp.get("learned") or {}).items():
            # ถือว่าอ่านจบแล้ว: ชั่วโมงเต็มถูกบันทึกไว้ครบ ทั้งสองฝั่งจึงไม่เอาเข้าคิวอ่าน
            t = syllabus.find_topic(code)[1]
            js["topics"][code] = {"hoursDone": t.hours, "learnedOn": ymd(learned_off),
                                  "rep": rep, "next": ymd(learned_off + 7)}
            py["topics"][code] = {"hours_done": t.hours, "learned_on": ymd(learned_off),
                                  "repetition": rep, "next_review": ymd(learned_off + 7)}
        for code, (seen, ok) in (sp.get("quiz") or {}).items():
            # กระจายสถิติลงข้อจริงในหัวข้อนั้น เพื่อให้สองฝั่งได้ความแม่นเท่ากัน
            qids = [q for q in QIDS_BY_TOPIC.get(code, [])][:1]
            if not qids:
                raise SystemExit(f"ไม่มีข้อสอบในหัวข้อ {code} — แก้ scenario")
            js["q"][qids[0]] = {"seen": seen, "ok": ok}
            py["questions"][qids[0]] = {"topic": code, "seen": seen, "correct": ok}
        entries = sp.get("today_log") or []
        if entries:
            js["log"][start.isoformat()] = [
                {"topic": c, "kind": "learn", "hours": h} for c, h in entries]
            js["days"][start.isoformat()] = sum(h for _, h in entries)
            py["day_log"][start.isoformat()] = [
                {"topic": c, "kind": "learn", "hours": h} for c, h in entries]
            py["study_log"][start.isoformat()] = sum(h for _, h in entries)
            # ชั่วโมงที่ทำไปแล้วต้องถูกบวกเข้า hours_done ด้วย ไม่งั้นสองฝั่งเห็นคนละสถานะ
            for c, h in entries:
                js["topics"].setdefault(c, {})
                py["topics"].setdefault(c, {})
                js["topics"][c]["hoursDone"] = js["topics"][c].get("hoursDone", 0) + h
                py["topics"][c]["hours_done"] = py["topics"][c].get("hours_done", 0) + h
        out.append((name, js, py))
    return out


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 250
    start = date.today()
    bad = 0
    for name, js_seed, py_seed in scenarios(start):
        j = js_plan(start, n, js_seed)
        p = py_plan(start, n, py_seed)
        pairs = list(zip(j, p))
        diff = [a["date"] for a, b in pairs if a["blocks"] != b["blocks"]]
        dup_py, dup_js = dups(p), dups(j)
        ok = not diff and not dup_py and not dup_js
        bad += 0 if ok else 1
        print(f"\n{'✅' if ok else '❌'} {name}  ({len(pairs)} วัน จาก {start})")
        print(f"     ตารางไม่ตรงกัน {len(diff)} วัน · Python จัดซ้ำ {len(dup_py)} วัน"
              f" · JS จัดซ้ำ {len(dup_js)} วัน")
        for dt in diff[:3]:
            a = next(x for x in j if x["date"] == dt)
            b = next(x for x in p if x["date"] == dt)
            print(f"       {dt}\n         JS: {a['blocks']}\n         PY: {b['blocks']}")

    print("\n✅ ตรงกันทุกสถานการณ์" if not bad else f"\n❌ ยังไม่ตรง {bad} สถานการณ์")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
