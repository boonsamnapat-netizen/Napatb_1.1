"""รวมข้อมูลทั้งระบบเป็น JSON ก้อนเดียว แล้วฝังลงหน้าเว็บ.

หน้าเว็บ (`web/tcas_app.html`) เป็นไฟล์ template ที่มีตัวคั่น
`/*__TCAS_DATA__*/` อยู่ข้างใน — ตอน export เราแทนที่ตรงนั้นด้วย JSON จริง
ได้ไฟล์ HTML ไฟล์เดียวที่เปิดได้เลย ไม่ต้องมีเซิร์ฟเวอร์ ไม่ต้องต่อเน็ต

ข้อมูลที่ฝัง = ตารางอ่าน + ตารางทดสอบ + คลังข้อสอบ + วันสอบ + คณะ
รันใหม่เมื่อไรก็ได้เมื่อแก้ config หรือเพิ่มข้อสอบ:

    python tcas_cli.py export
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import icons, planner, ranking, scoring, syllabus, testplan
from .config import REPO_ROOT, exam_dates, parse_date, resolve_path
from .models import StudyDay

# ตัวคั่นกินค่า null ที่ตามมาด้วย เพื่อให้ผลลัพธ์เป็น `const DATA = {...};`
# ไม่ใช่ `const DATA = {...} null;` ซึ่งเป็น syntax error
# template ดิบ (ที่ยังไม่ได้ฝังข้อมูล) จึงยังเป็น JS ที่ถูกต้อง เปิดดูโครงหน้าได้
DATA_MARKER = "/*__TCAS_DATA__*/null"
DEFAULT_TEMPLATE = REPO_ROOT / "web" / "tcas_app.html"
DEFAULT_OUTPUT = REPO_ROOT / "web" / "tcas_app.build.html"


def _day_payload(sd: StudyDay) -> Dict[str, Any]:
    return {
        "date": sd.day.isoformat(),
        "hours": round(sd.hours, 2),
        "note": sd.note,
        "blocks": [
            {
                "subject": b.subject_code,
                "subjectName": b.subject_name,
                "topic": b.topic_code,
                "topicName": b.topic_name,
                "hours": round(b.hours, 2),
                "kind": b.kind,
                "repetition": b.repetition,
            }
            for b in sd.blocks
        ],
    }


def build_payload(
    cfg: Dict[str, Any],
    store,
    programs: Optional[Dict[str, Any]],
    bank: Dict[str, Any],
    start: date,
    horizon_days: int = 400,
) -> Dict[str, Any]:
    """สร้าง dict ที่จะกลายเป็น JSON ฝังในหน้าเว็บ."""
    plan = planner.generate_plan(cfg, store, start=start, max_days=horizon_days)
    tests = testplan.generate(cfg, plan, start, bank=bank)

    subjects = {
        code: {
            "name": subj.name,
            "short": subj.label,
            "exam": subj.exam,
            "group": subj.group,
            "maxScore": subj.max_score,
            "hours": round(subj.total_hours, 1),
            "topics": [
                {
                    "code": t.code,
                    "name": t.name,
                    "weight": t.weight,
                    "hours": t.hours,
                }
                for t in subj.topics
            ],
        }
        for code, subj in syllabus.SUBJECTS.items()
    }

    questions = [
        {
            "qid": q.qid,
            "subject": q.subject_code,
            "topic": q.topic_code,
            "stem": q.stem,
            "choices": list(q.choices),
            "answer": q.answer,
            "explanation": q.explanation,
            "difficulty": q.difficulty,
        }
        for q in bank.values()
    ]

    exam_specs = exam_dates(cfg)
    exams = [
        {
            "key": key,
            "name": spec["name"],
            "date": spec["date"].isoformat(),
            "verified": spec["verified"],
            # ตัวนับถอยหลังหลักจะยึดเฉพาะสนามที่ counts = true
            "counts": spec["counts"],
        }
        for key, spec in exam_specs.items()
    ]

    # เส้นตายของแต่ละวิชา — ใช้ให้เบราว์เซอร์คำนวณความเร่งด่วนเองได้
    tpat1_day = exam_specs.get("tpat1", {}).get("date")
    alevel_day = exam_specs.get("alevel", {}).get("date")
    deadlines = {
        code: (tpat1_day if subj.exam == "tpat1" else alevel_day).isoformat()
        for code, subj in syllabus.SUBJECTS.items()
        if (tpat1_day if subj.exam == "tpat1" else alevel_day)
    }

    # config การวางแผน — เบราว์เซอร์ใช้จัดตารางใหม่จากสิ่งที่ยังไม่ได้ทำจริง
    # แทนที่จะยึดปฏิทินที่คำนวณไว้ตอน build (ซึ่งตามหลังไม่ได้)
    st = cfg.get("study") or {}
    study = {
        "hoursByWeekday": st.get("hours_by_weekday") or {},
        "blockHours": float(st.get("block_hours", 1.5)),
        "reviewShare": float(st.get("review_share", 0.25)),
        "reviewIntervals": list(st.get("review_intervals_days") or [1, 3, 7, 16, 35]),
        "daysOff": [str(d) for d in (st.get("days_off") or [])],
        "baselineMastery": float(cfg.get("baseline_mastery", 35.0)),
        "deadlines": deadlines,
    }

    milestones = [
        {"date": parse_date(m["date"]).isoformat(), "label": str(m.get("label", ""))}
        for m in (cfg.get("milestones") or [])
    ]

    program_list: List[Dict[str, Any]] = []
    if programs:
        for c in ranking.rank(programs, None):
            program_list.append(
                {
                    "code": c.code,
                    "name": c.name,
                    "faculty": c.faculty,
                    "seats": c.seats,
                    "projected": c.projected_cutoff,
                    "trend": c.trend,
                    "verified": c.verified,
                }
            )

    return {
        "generatedAt": date.today().isoformat(),
        "startDate": start.isoformat(),
        "student": cfg.get("student") or {},
        "exams": exams,
        "study": study,
        "milestones": milestones,
        "weights": scoring.group_weights(cfg),
        "groupLabels": scoring.GROUP_LABELS,
        "minimums": (cfg.get("kaspot") or {}).get("minimums") or {},
        "subjects": subjects,
        "plan": [_day_payload(sd) for sd in plan],
        "tests": [
            {
                "date": e.day.isoformat(),
                "kind": e.kind,
                "kindLabel": testplan.KIND_LABELS.get(e.kind, e.kind),
                "title": e.title,
                "subjects": e.subjects,
                "topics": e.topics,
                "questions": e.questions,
                "minutes": e.minutes,
                "note": e.note,
            }
            for e in tests
        ],
        "questions": questions,
        "programs": program_list,
    }


def render(payload: Dict[str, Any], template: str | Path | None = None) -> str:
    """ฝัง payload ลง template คืนเป็นสตริง HTML ที่สมบูรณ์."""
    path = resolve_path(template) if template else DEFAULT_TEMPLATE
    if not path.exists():
        raise FileNotFoundError(f"ไม่พบไฟล์ template: {path}")
    html = path.read_text(encoding="utf-8")
    if DATA_MARKER not in html:
        raise ValueError(
            f"template ไม่มีตัวคั่น {DATA_MARKER} — ใส่ไว้ตรงที่ต้องการให้ข้อมูลไปอยู่"
        )
    # </script> ใน string ของ JSON จะไปปิด <script> ของหน้าเว็บก่อนเวลา
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return html.replace(DATA_MARKER, blob)


def write(html: str, output: str | Path | None = None) -> Path:
    path = resolve_path(output) if output else DEFAULT_OUTPUT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


# ══════════════════════════════════════════════════════════════════════
# โหมด PWA — สร้างเป็นโฟลเดอร์เว็บไซต์ ติดตั้งลงหน้าจอโฮมได้
# ══════════════════════════════════════════════════════════════════════
DEFAULT_SITE = REPO_ROOT / "web" / "dist"

APP_NAME = "TCAS70 เตรียมสอบแพทย์"
APP_SHORT = "TCAS70"
THEME_COLOR = "#101826"

TITLE_RE = re.compile(r"<title>(.*?)</title>\s*", re.S)


def _document(content: str, title: str) -> str:
    """ห่อเนื้อหาให้เป็น HTML เต็มรูปแบบ.

    template ตั้งใจเขียนเป็น 'เนื้อหาอย่างเดียว' เพื่อให้ publish เป็น Artifact ได้
    แต่ PWA ต้องคุม <head> เอง (manifest, theme-color, meta ของ iOS) จึงห่อตรงนี้
    """
    return f"""<!doctype html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{title}</title>
<meta name="description" content="ตารางอ่านหนังสือ ตารางทดสอบ และคลังข้อสอบ TCAS70 กสพท">
<meta name="theme-color" content="{THEME_COLOR}">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="icon-192.png" sizes="192x192">
<link rel="apple-touch-icon" href="icon-180.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="{APP_SHORT}">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="mobile-web-app-capable" content="yes">
</head>
<body>
{content}
<script>
/* ลงทะเบียน service worker เพื่อให้ใช้ได้ตอนไม่มีเน็ต
   ต้องเสิร์ฟผ่าน https (หรือ localhost) — เปิดไฟล์ตรง ๆ ด้วย file:// จะข้ามไป */
if ("serviceWorker" in navigator && location.protocol.startsWith("http")) {{
  window.addEventListener("load", () => {{
    navigator.serviceWorker.register("sw.js").catch(err =>
      console.warn("service worker ลงทะเบียนไม่สำเร็จ:", err));
  }});
}}
</script>
</body>
</html>
"""


def _manifest() -> str:
    return json.dumps(
        {
            "name": APP_NAME,
            "short_name": APP_SHORT,
            "description": "ตารางอ่านหนังสือ ตารางทดสอบ และคลังข้อสอบ กสพท",
            "lang": "th",
            "dir": "ltr",
            "start_url": ".",
            "scope": ".",
            "display": "standalone",
            "orientation": "portrait",
            "background_color": THEME_COLOR,
            "theme_color": THEME_COLOR,
            "icons": [
                {"src": "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
                {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def _service_worker(version: str) -> str:
    """cache-first สำหรับ app shell.

    ข้อมูลทั้งหมดฝังอยู่ใน index.html แล้ว จึงไม่มีอะไรต้องเรียกผ่านเน็ตตอนใช้งาน
    version เปลี่ยนทุกครั้งที่ build ใหม่ -> แคชเก่าถูกลบและโหลดของใหม่
    """
    return f"""/* TCAS70 — service worker (build {version}) */
const CACHE = "tcas70-{version}";
const SHELL = ["./", "./index.html", "./manifest.webmanifest",
               "./icon-192.png", "./icon-512.png", "./icon-180.png"];

self.addEventListener("install", e => {{
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
}});

self.addEventListener("activate", e => {{
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
}});

self.addEventListener("fetch", e => {{
  if (e.request.method !== "GET") return;
  const url = new URL(e.request.url);
  if (url.origin !== location.origin) return;

  // ตารางทั้งหมดฝังอยู่ใน index.html ดังนั้นตัวหน้าเว็บ = ตัวข้อมูล
  // จึงต้องเอาของใหม่ก่อนถ้าเน็ตมี ไม่งั้น build ใหม่จะไม่ขึ้นจนกว่าจะโหลดสองรอบ
  const isPage = e.request.mode === "navigate" ||
                 e.request.destination === "document" ||
                 url.pathname.endsWith("/") ||
                 url.pathname.endsWith("index.html");

  if (isPage) {{
    e.respondWith(
      fetch(e.request)
        .then(res => {{
          if (res && res.ok) {{
            const copy = res.clone();
            caches.open(CACHE).then(c => c.put("./index.html", copy));
          }}
          return res;
        }})
        .catch(() => caches.match("./index.html").then(hit => hit || Response.error()))
    );
    return;
  }}

  // ไอคอน/manifest ไม่ค่อยเปลี่ยน — เอาจากแคชก่อนเพื่อความเร็ว แล้วค่อยอัปเดตเบื้องหลัง
  e.respondWith(
    caches.match(e.request).then(hit => {{
      if (hit) {{
        fetch(e.request)
          .then(res => res && res.ok && caches.open(CACHE).then(c => c.put(e.request, res.clone())))
          .catch(() => {{}});
        return hit;
      }}
      return fetch(e.request).catch(() => Response.error());
    }})
  );
}});
"""


def build_site(
    payload: Dict[str, Any],
    outdir: str | Path | None = None,
    template: str | Path | None = None,
) -> Dict[str, Any]:
    """สร้างโฟลเดอร์เว็บไซต์ PWA พร้อม deploy."""
    out = resolve_path(outdir) if outdir else DEFAULT_SITE
    out.mkdir(parents=True, exist_ok=True)

    content = render(payload, template)
    match = TITLE_RE.search(content)
    title = match.group(1) if match else APP_NAME
    content = TITLE_RE.sub("", content, count=1)

    # ผูก version ของแคชกับเนื้อหาจริง — เนื้อหาเปลี่ยนเมื่อไร แคชล้างเมื่อนั้น
    version = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]

    (out / "index.html").write_text(_document(content, title), encoding="utf-8")
    (out / "manifest.webmanifest").write_text(_manifest(), encoding="utf-8")
    (out / "sw.js").write_text(_service_worker(version), encoding="utf-8")
    # Pages ไม่ต้องประมวลผลด้วย Jekyll — กันไฟล์ที่ขึ้นต้นด้วย _ โดนตัดทิ้ง
    (out / ".nojekyll").write_text("", encoding="utf-8")
    icons.write_all(out)

    return {
        "dir": out,
        "version": version,
        "files": sorted(p.name for p in out.iterdir()),
        "bytes": sum(p.stat().st_size for p in out.iterdir() if p.is_file()),
    }
