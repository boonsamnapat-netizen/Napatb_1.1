#!/usr/bin/env python3
"""TCAS70 — ระบบเตรียมสอบแพทย์ (กสพท).

ตัวอย่างการใช้งาน
    python tcas_cli.py today                        ตารางวันนี้ + คิวทบทวน
    python tcas_cli.py plan --days 14               ตารางล่วงหน้า 14 วัน
    python tcas_cli.py plan --subject bio --days 7  เฉพาะวิชาเดียว
    python tcas_cli.py done bio_cell                บันทึกว่าอ่านหัวข้อนี้จบแล้ว
    python tcas_cli.py quiz --subject bio -n 5      ทำข้อสอบ 5 ข้อ
    python tcas_cli.py quiz --subject bio --auto    ดูข้อสอบ+เฉลย ไม่ต้องพิมพ์ตอบ
    python tcas_cli.py score --set tpat1=210 --set bio=72
    python tcas_cli.py score --from-mastery         ประมาณคะแนนจากผล quiz
    python tcas_cli.py rank --score 70.5            จัดอันดับคณะ
    python tcas_cli.py progress                     ความคืบหน้ารายวิชา
    python tcas_cli.py bank                         ดูว่าคลังข้อสอบมีอะไรบ้าง
    python tcas_cli.py notify                       ส่งสรุปเช้าเข้า Telegram

ทุกคำสั่งรับ --config เพื่อชี้ไฟล์ config อื่น และ --date เพื่อจำลองวันที่
"""

from __future__ import annotations

import argparse
import html
import random
import re
import sys
from datetime import timedelta

from src.tcas import config as cfgmod
from src.tcas import verify
from src.tcas import planner, quiz, ranking, report, scoring, srs, syllabus
from src.tcas.notifier import TelegramNotifier
from src.tcas.store import ProgressStore

TAG_RE = re.compile(r"<[^>]+>")


def show(text: str) -> None:
    """พิมพ์ข้อความที่เขียนด้วย HTML tag ของ Telegram ให้อ่านได้บนเทอร์มินัล."""
    print(html.unescape(TAG_RE.sub("", text)))


def _load(args):
    cfg = cfgmod.load_config(args.config)
    store = ProgressStore((cfg.get("storage") or {}).get("progress_file", "data/tcas/progress.json"))
    on = cfgmod.today(args.date)
    return cfg, store, on


# ------------------------------------------------------------------ commands
def cmd_today(args) -> int:
    cfg, store, on = _load(args)
    sd = planner.plan_for_day(cfg, store, on)
    show(report.countdown(cfg, on))
    print()
    milestones = report.upcoming_milestones(cfg, on)
    if milestones:
        show(milestones)
        print()
    show(report.study_day(sd))
    due = store.due_reviews(on)
    if due:
        print(f"\nค้างทบทวน {len(due)} หัวข้อ:")
        for code, _ in due[:10]:
            _, topic = syllabus.find_topic(code)
            if topic:
                print(f"  • {topic.name}  ({code})")
    return 0


def cmd_plan(args) -> int:
    cfg, store, on = _load(args)
    end = on + timedelta(days=args.days - 1) if args.days else None
    subjects = args.subject or None
    if subjects:
        for s in subjects:
            syllabus.get_subject(s)  # ตรวจว่ามีวิชานี้จริงก่อนคำนวณยาว ๆ
    plan = planner.generate_plan(cfg, store, start=on, end=end, subjects=subjects)
    show(report.plan_summary(plan, limit=args.days or 7))
    return 0


def cmd_done(args) -> int:
    """บันทึกว่าอ่านหัวข้อจบแล้ว -> เข้าคิวทบทวนอัตโนมัติ."""
    cfg, store, on = _load(args)
    intervals = list((cfg.get("study") or {}).get("review_intervals_days") or srs.DEFAULT_INTERVALS)

    marked = []
    for code in args.topic:
        subj, topic = syllabus.find_topic(code)
        if topic is None:
            print(f"ไม่รู้จักหัวข้อ '{code}' — ดูรหัสหัวข้อได้จาก: python tcas_cli.py topics")
            return 1
        store.set_topic(code, **srs.first_schedule(on, intervals))
        store.log_study(on, topic.hours)
        marked.append((subj, topic))

    store.save()
    for subj, topic in marked:
        nxt = store.topic(topic.code)["next_review"]
        print(f"✅ {subj.name} · {topic.name} — ทบทวนครั้งแรก {nxt}")
    return 0


def cmd_topics(args) -> int:
    _cfg, store, _on = _load(args)
    baseline = float(_cfg.get("baseline_mastery", 35.0))
    for code, subj in syllabus.SUBJECTS.items():
        if args.subject and code not in args.subject:
            continue
        print(f"\n{subj.name}  [{code}]  {subj.total_hours:.0f} ชม.")
        for t in subj.topics:
            mark = "✅" if store.is_learned(t.code) else "  "
            mastery = store.mastery(t.code, baseline)
            print(
                f"  {mark} {t.code:24s} w{t.weight} {t.hours:4.1f}ชม. "
                f"แม่น {mastery:5.1f}%  {t.name}"
            )
    return 0


def cmd_bank(args) -> int:
    cfg, _store, _on = _load(args)
    qdir = (cfg.get("quiz") or {}).get("questions_dir", "data/tcas/questions")
    try:
        bank = quiz.load_bank(qdir)
    except quiz.BankError as exc:
        print(f"คลังข้อสอบมีปัญหา: {exc}")
        return 1
    if not bank:
        print(f"ยังไม่มีข้อสอบใน {qdir}")
        return 0

    stats = quiz.bank_stats(bank)
    print(f"คลังข้อสอบทั้งหมด {len(bank)} ข้อ\n")
    for subject_code in sorted(stats):
        subj = syllabus.SUBJECTS.get(subject_code)
        name = subj.name if subj else subject_code
        rows = stats[subject_code]
        print(f"{name}  ({rows['total']} ข้อ)")
        for topic_code, n in sorted(rows.items()):
            if topic_code == "total":
                continue
            _, topic = syllabus.find_topic(topic_code)
            print(f"    {n:3d}  {topic.name if topic else topic_code}")
        # หัวข้อที่ยังไม่มีข้อสอบเลย — บอกไว้เพื่อให้รู้ว่าคลังยังขาดตรงไหน
        if subj:
            gaps = [t for t in subj.topics if t.code not in rows]
            if gaps:
                print(f"    ยังไม่มีข้อสอบ {len(gaps)} หัวข้อ: "
                      + ", ".join(t.code for t in gaps[:6])
                      + (" …" if len(gaps) > 6 else ""))
        print()
    return 0


def cmd_quiz(args) -> int:
    cfg, store, on = _load(args)
    qdir = (cfg.get("quiz") or {}).get("questions_dir", "data/tcas/questions")
    try:
        bank = quiz.load_bank(qdir)
    except quiz.BankError as exc:
        print(f"คลังข้อสอบมีปัญหา: {exc}")
        return 1

    count = args.n or int((cfg.get("quiz") or {}).get("default_count", 10))
    rng = random.Random(args.seed) if args.seed is not None else random.Random()
    questions = quiz.select_questions(
        bank, store, on,
        subject=args.subject, topic=args.topic,
        count=count, mode=args.mode, rng=rng,
    )
    if not questions:
        print("ไม่มีข้อสอบที่ตรงเงื่อนไข — ลอง --mode all หรือเพิ่มข้อสอบใน data/tcas/questions/")
        return 0

    answers = []
    for i, q in enumerate(questions, start=1):
        print("\n" + "─" * 60)
        print(quiz.render_question(q, i, len(questions)))
        if args.auto:
            # โหมดดูอย่างเดียว: ไม่บันทึกสถิติ ใช้ตอนอ่านทบทวนหรือรันใน CI
            print(f"\n  เฉลย: {q.answer_label()}")
            if q.explanation:
                print(f"  {q.explanation}")
            continue
        try:
            raw = input("\nตอบ (ก/ข/ค/ง หรือ 1-4, Enter = ข้าม): ")
        except (EOFError, KeyboardInterrupt):
            print("\nยกเลิก — ข้อที่ทำไปแล้วยังไม่ถูกบันทึก")
            return 130
        given = quiz.parse_answer(raw, len(q.choices))
        answers.append(given)
        if given == q.answer:
            print("  ✅ ถูกต้อง")
        else:
            print(f"  ❌ ผิด — เฉลย: {q.answer_label()}")
        if q.explanation:
            print(f"  {q.explanation}")

    if args.auto:
        print(f"\n(โหมด --auto: แสดง {len(questions)} ข้อพร้อมเฉลย ไม่บันทึกสถิติ)")
        return 0

    result = quiz.grade(questions, answers, store, cfg, on)
    store.save()
    print("\n" + "═" * 60)
    show(report.quiz_result(result, bank))

    if args.notify:
        TelegramNotifier(cfg).send(report.quiz_result(result, bank))
    return 0


def _parse_set(pairs) -> dict:
    """แปลง --set bio=72 เป็น {'bio': 72.0} พร้อมตรวจชื่อวิชาและช่วงคะแนน."""
    out = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise SystemExit(f"รูปแบบต้องเป็น วิชา=คะแนน เช่น bio=72 (ได้รับ '{pair}')")
        code, _, raw = pair.partition("=")
        code = code.strip()
        subj = syllabus.SUBJECTS.get(code)
        if subj is None:
            raise SystemExit(
                f"ไม่รู้จักวิชา '{code}' — ใช้ได้: {', '.join(sorted(syllabus.SUBJECTS))}"
            )
        try:
            value = float(raw)
        except ValueError:
            raise SystemExit(f"คะแนนของ '{code}' ต้องเป็นตัวเลข (ได้รับ '{raw}')")
        if not 0 <= value <= subj.max_score:
            raise SystemExit(
                f"คะแนน '{code}' ต้องอยู่ระหว่าง 0 ถึง {subj.max_score:.0f} (ได้รับ {value})"
            )
        out[code] = value
    return out


def cmd_score(args) -> int:
    cfg, store, _on = _load(args)

    if args.from_mastery:
        raw = scoring.project_from_mastery(cfg, store)
        print("ประมาณคะแนนจากความแม่นที่สะสมจาก quiz (ไม่ใช่คะแนนสอบจริง)\n")
    else:
        new = _parse_set(args.set)
        for code, value in new.items():
            store.set_score(code, value)
        if new:
            store.save()
        raw = store.scores()

    if not raw:
        print("ยังไม่มีคะแนน — กรอกด้วย: python tcas_cli.py score --set tpat1=210 --set bio=72")
        print("หรือประมาณจากผล quiz ด้วย: python tcas_cli.py score --from-mastery")
        return 0

    card = scoring.compute(cfg, raw)
    print("คะแนนดิบที่ใช้:")
    for code in sorted(raw):
        subj = syllabus.SUBJECTS.get(code)
        if subj:
            print(f"  {subj.name:38s} {raw[code]:6.1f} / {subj.max_score:.0f}")
    print()
    show(report.score_card(card, cfg))

    if args.target:
        need = scoring.required_percent(cfg, raw, args.target)
        print()
        if need is None:
            gap = args.target - card.total
            verdict = "ถึงเป้าแล้ว ✅" if gap <= 0 else f"ยังขาดอีก {gap:.2f} คะแนน"
            print(f"เป้าหมาย {args.target:.2f} — {verdict}")
        elif need > 100:
            print(f"เป้าหมาย {args.target:.2f} — ไปไม่ถึงแล้ว แม้ทำวิชาที่เหลือได้เต็ม 100%")
        else:
            print(f"เป้าหมาย {args.target:.2f} — ต้องทำวิชาที่ยังไม่ได้กรอกให้ได้เฉลี่ย {need:.1f}%")
    return 0


def cmd_rank(args) -> int:
    cfg, store, _on = _load(args)
    programs = cfgmod.load_programs(args.programs)

    # ลำดับความสำคัญ: --score ที่ระบุเอง > --from-mastery > คะแนนที่เคยกรอกไว้
    my_score = args.score
    if my_score is None:
        if args.from_mastery:
            my_score = scoring.compute(cfg, scoring.project_from_mastery(cfg, store)).total
        elif store.scores():
            my_score = scoring.compute(cfg, store.scores()).total

    chances = ranking.rank(programs, my_score, faculty=args.faculty)
    if not chances:
        print("ไม่มีคณะที่ตรงเงื่อนไข")
        return 0

    show(report.program_ranking(chances, my_score, limit=args.limit))
    if my_score is not None:
        print()
        show(report.order_suggestion(chances))
    else:
        print("\n(ยังไม่มีคะแนน — ระบุด้วย --score 70.5 หรือกรอกด้วยคำสั่ง score ก่อน)")
    return 0


def cmd_progress(args) -> int:
    cfg, store, on = _load(args)
    show(report.coverage(cfg, store))
    log = store.data.get("quiz_log") or []
    if log:
        print(f"\nทำข้อสอบไปแล้ว {len(log)} ชุด — 5 ชุดล่าสุด:")
        for entry in log[-5:]:
            print(
                f"  {entry['date']}  {entry['subject']:6s} "
                f"{entry['correct']}/{entry['total']} ({entry['pct']}%)"
            )
    hours = sum(float(v) for v in (store.data.get("study_log") or {}).values())
    if hours:
        print(f"\nชั่วโมงที่บันทึกไว้ทั้งหมด: {hours:.1f} ชม.")
    due = store.due_reviews(on)
    print(f"คิวทบทวนที่ถึงกำหนดวันนี้: {len(due)} หัวข้อ")
    return 0


def cmd_export(args) -> int:
    """สร้างหน้าเว็บไฟล์เดียวที่มีตารางอ่าน ตารางทดสอบ และคลังข้อสอบฝังอยู่."""
    from src.tcas import webexport

    cfg, store, on = _load(args)
    qdir = (cfg.get("quiz") or {}).get("questions_dir", "data/tcas/questions")
    try:
        bank = quiz.load_bank(qdir)
    except quiz.BankError as exc:
        print(f"คลังข้อสอบมีปัญหา: {exc}")
        return 1

    try:
        programs = cfgmod.load_programs(args.programs)
    except FileNotFoundError:
        programs = None

    resources = cfgmod.load_resources(args.resources)
    payload = webexport.build_payload(
        cfg, store, programs, bank, start=on, resources=resources)
    summary = (
        f"  ตารางอ่าน {len(payload['plan'])} วัน · "
        f"ตารางทดสอบ {len(payload['tests'])} ครั้ง · "
        f"ข้อสอบ {len(payload['questions'])} ข้อ"
    )

    try:
        if args.single:
            html = webexport.render(payload, args.template)
            path = webexport.write(html, args.out)
            print(f"สร้างไฟล์เดียวแล้ว: {path}  ({path.stat().st_size / 1024:.0f} KB)")
            print(summary)
            print("  เปิดในเบราว์เซอร์ได้เลย ไม่ต้องต่อเน็ต (ติดตั้งเป็นแอปไม่ได้)")
        else:
            site = webexport.build_site(payload, args.out, args.template)
            print(f"สร้างเว็บแอปแล้ว: {site['dir']}  ({site['bytes'] / 1024:.0f} KB)")
            print(summary)
            print(f"  ไฟล์: {', '.join(site['files'])}")
            print(f"  build {site['version']}")
            print("  ทดสอบเครื่องตัวเอง: python -m http.server -d web/dist 8000")
            print("  แล้วเปิด http://localhost:8000 (ต้องผ่าน http ไม่ใช่ file://)")
    except (FileNotFoundError, ValueError) as exc:
        print(f"สร้างหน้าเว็บไม่สำเร็จ: {exc}")
        return 1
    return 0


def cmd_tests(args) -> int:
    """ดูตารางทดสอบบนเทอร์มินัล."""
    from src.tcas import testplan

    cfg, store, on = _load(args)
    qdir = (cfg.get("quiz") or {}).get("questions_dir", "data/tcas/questions")
    try:
        bank = quiz.load_bank(qdir)
    except quiz.BankError as exc:
        print(f"คลังข้อสอบมีปัญหา: {exc}")
        return 1
    plan = planner.generate_plan(cfg, store, start=on)
    events = testplan.generate(cfg, plan, on, bank=bank)
    if args.kind:
        events = [e for e in events if e.kind == args.kind]
    if not events:
        print("ไม่มีการทดสอบในช่วงนี้")
        return 0

    for e in events[: args.limit]:
        days = (e.day - on).days
        when = "วันนี้" if days == 0 else f"อีก {days} วัน"
        print(f"\n{e.day}  ({when})  [{testplan.KIND_LABELS.get(e.kind, e.kind)}]")
        print(f"  {e.title}")
        if e.subjects:
            print(f"  วิชา: {', '.join(e.subject_names)}")
        if e.questions:
            print(f"  ประมาณ {e.questions} ข้อ · {e.minutes} นาที")
        elif e.minutes:
            print(f"  ใช้เวลา {e.minutes} นาที")
        if e.note:
            print(f"  {e.note}")
    return 0


def cmd_cutoff(args) -> int:
    """กรอกคะแนนต่ำสุดของคณะจากบรรทัดคำสั่ง แทนการแก้ YAML ด้วยมือ

    เหตุผลที่ต้องมี: คณะในระบบมี 57 รายการ และ 41 รายการยังไม่มีคะแนน
    การเปิดไฟล์แก้ทีละอันทั้งเสียเวลาและพลาดง่าย (เยื้อง, ตัวเลขผิดช่อง)
    คำสั่งนี้แก้ให้ตรงคณะ ตรวจค่าให้ และตั้ง verified: true ให้ในคราวเดียว

        python tcas_cli.py cutoff tu_dent 2568=70.4 2569=70.6
        python tcas_cli.py cutoff --list ทันตแพทยศาสตร์
    """
    import yaml as _yaml

    path = cfgmod.DEFAULT_PROGRAMS
    doc = _yaml.safe_load(open(path, encoding="utf-8")) or {}
    progs = doc.get("programs") or []

    if args.list is not None:
        want = (args.list or "").strip()
        rows = [p for p in progs if not want or want in str(p.get("faculty", ""))]
        if not rows:
            print(f"ไม่พบคณะที่ตรงกับ '{want}' — กลุ่มที่มี: "
                  + ", ".join(sorted({str(p.get("faculty")) for p in progs})))
            return 1
        print(f"{'code':16s} {'คะแนนต่ำสุดที่มี':>22s}  ชื่อ")
        for p in rows:
            cut = p.get("cutoffs") or {}
            mark = "✓" if p.get("verified") else ("~" if cut else "—")
            txt = ", ".join(f"{y}:{v}" for y, v in sorted(cut.items())) or "ยังไม่มี"
            print(f"{p.get('code',''):16s} {mark} {txt:>20s}  {p.get('name','')}")
        print("\n✓ = ยืนยันแล้ว · ~ = มีตัวเลขแต่ยังไม่ยืนยัน · — = ยังไม่มี")
        return 0

    target = next((p for p in progs if p.get("code") == args.code), None)
    if target is None:
        print(f"ไม่พบรหัสคณะ '{args.code}' — ดูรายการทั้งหมดด้วย --list")
        return 1

    if not args.pairs:
        print("ต้องระบุคะแนนอย่างน้อยหนึ่งปี เช่น  2569=70.6")
        return 1

    cutoffs = dict(target.get("cutoffs") or {})
    for pair in args.pairs:
        if "=" not in pair:
            print(f"รูปแบบไม่ถูกต้อง: '{pair}' — ต้องเป็น ปี=คะแนน เช่น 2569=70.6")
            return 1
        year_s, score_s = pair.split("=", 1)
        try:
            year, score = int(year_s), float(score_s)
        except ValueError:
            print(f"อ่านค่าไม่ได้: '{pair}'")
            return 1
        # คะแนน กสพท เต็ม 100 — ค่านอกช่วงนี้แปลว่ากรอกผิดช่องแน่ ๆ
        if not 0 <= score <= 100:
            print(f"คะแนน {score} อยู่นอกช่วง 0-100 — ตรวจอีกครั้งว่าไม่ได้กรอกคะแนนดิบ")
            return 1
        if not 2500 <= year <= 2600:
            print(f"ปี {year} ไม่น่าใช่ พ.ศ. — ใช้ปีการศึกษาแบบ 2569")
            return 1
        cutoffs[year] = score

    cutoffs = dict(sorted(cutoffs.items()))
    verified = not args.unverified

    # แก้เป็นข้อความทีละบรรทัด ไม่ใช้ yaml.safe_dump เขียนทับทั้งไฟล์
    # เพราะ dump จะล้างคอมเมนต์ทิ้งหมด รวมถึงคำเตือนเรื่องข้อมูลที่ยังไม่ยืนยัน
    # ซึ่งเป็นส่วนที่ต้องอยู่ให้นานที่สุด
    lines = open(path, encoding="utf-8").read().split("\n")
    start = next(i for i, l in enumerate(lines)
                 if re.match(rf"\s*-\s*code:\s*{re.escape(args.code)}\s*$", l))
    end = next((i for i in range(start + 1, len(lines))
                if re.match(r"\s*-\s+code:", lines[i])), len(lines))

    cut_txt = "{" + ", ".join(f"{y}: {v}" for y, v in cutoffs.items()) + "}"
    block = lines[start:end]
    seen_cut = seen_ver = False
    for i, l in enumerate(block):
        if re.match(r"\s*cutoffs:", l):
            block[i] = f"    cutoffs: {cut_txt}"
            seen_cut = True
        elif re.match(r"\s*verified:", l):
            block[i] = f"    verified: {str(verified).lower()}"
            seen_ver = True
    # คณะที่ยังไม่เคยมีสองบรรทัดนี้ (ไม่น่าเกิด แต่กันไว้) ให้เติมท้ายบล็อก
    tail = len(block)
    while tail > 0 and not block[tail - 1].strip():
        tail -= 1
    if not seen_cut:
        block.insert(tail, f"    cutoffs: {cut_txt}"); tail += 1
    if not seen_ver:
        block.insert(tail, f"    verified: {str(verified).lower()}")

    lines[start:end] = block
    open(path, "w", encoding="utf-8").write("\n".join(lines))

    # อ่านกลับมาตรวจว่าไฟล์ยังใช้ได้และค่าลงถูกที่จริง
    check = _yaml.safe_load(open(path, encoding="utf-8")) or {}
    got = next((x for x in (check.get("programs") or [])
                if x.get("code") == args.code), None)
    if got is None or got.get("cutoffs") != cutoffs or got.get("verified") != verified:
        print("เขียนไฟล์แล้วอ่านกลับมาไม่ตรง — กู้คืนด้วย git checkout config/tcas_programs.yaml")
        return 1

    state = "ยังไม่ยืนยัน" if args.unverified else "ยืนยันแล้ว"
    print(f"บันทึกแล้ว: {got.get('name')}")
    print("  คะแนนต่ำสุด: " + ", ".join(f"{y} → {v}" for y, v in cutoffs.items()))
    print(f"  สถานะ: {state}")
    print("\nรัน  python tcas_cli.py export  เพื่อให้เว็บแอปเห็นค่าใหม่")
    return 0


def cmd_verify(args) -> int:
    """ไล่รายการทุกค่าที่ยังไม่ได้ยืนยันกับประกาศจริง

    ออกด้วย exit code 1 ถ้ายังเหลือระดับ critical เพื่อให้เอาไปคั่นใน CI ได้
    ก่อนปล่อยเวอร์ชันที่มีคนใช้จริง
    """
    cfg = cfgmod.load_config(args.config)
    a = verify.audit(cfg)
    print(verify.render(a))
    if args.strict and a.counts().get("critical"):
        return 1
    return 0


def cmd_notify(args) -> int:
    cfg, store, on = _load(args)
    tg = TelegramNotifier(cfg)

    if args.test:
        ok = tg.send("✅ TCAS70 bot เชื่อมต่อแล้ว — พร้อมส่งตารางอ่านหนังสือทุกเช้า (ทดสอบ)")
        print("ส่งสำเร็จ" if ok else "dry-run: ยังไม่ได้ตั้ง secret หรือส่งไม่สำเร็จ")
        return 0

    sd = planner.plan_for_day(cfg, store, on)
    message = report.daily_brief(cfg, store, sd, on, include_coverage=not args.no_coverage)
    ok = tg.send(message)
    if ok:
        print("ส่งสรุปประจำวันเข้า Telegram แล้ว")
    return 0


# --------------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tcas_cli.py",
        description="TCAS70 — ระบบเตรียมสอบแพทย์ (กสพท)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--config", help="ไฟล์ config (ค่าเริ่มต้น config/tcas_config.yaml)")
    p.add_argument("--date", help="จำลองว่าวันนี้คือวันที่นี้ (YYYY-MM-DD)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("today", help="ตารางวันนี้ + นับถอยหลัง + คิวทบทวน")
    s.set_defaults(func=cmd_today)

    s = sub.add_parser("plan", help="ตารางอ่านหนังสือล่วงหน้า")
    s.add_argument("--days", type=int, default=7, help="จำนวนวัน (ค่าเริ่มต้น 7)")
    s.add_argument("--subject", action="append", help="จำกัดเฉพาะวิชานี้ (ใส่ซ้ำได้)")
    s.set_defaults(func=cmd_plan)

    s = sub.add_parser("done", help="บันทึกว่าอ่านหัวข้อจบแล้ว")
    s.add_argument("topic", nargs="+", help="รหัสหัวข้อ เช่น bio_cell")
    s.set_defaults(func=cmd_done)

    s = sub.add_parser("topics", help="รายการหัวข้อทั้งหมดพร้อมสถานะ")
    s.add_argument("--subject", action="append", help="จำกัดเฉพาะวิชานี้")
    s.set_defaults(func=cmd_topics)

    s = sub.add_parser("bank", help="สรุปคลังข้อสอบและช่องว่างที่ยังขาด")
    s.set_defaults(func=cmd_bank)

    s = sub.add_parser("quiz", help="ทำชุดข้อสอบ")
    s.add_argument("--subject", help="รหัสวิชา เช่น bio")
    s.add_argument("--topic", help="รหัสหัวข้อ เช่น bio_cell")
    s.add_argument("-n", type=int, help="จำนวนข้อ")
    s.add_argument(
        "--mode", default="mixed",
        choices=["mixed", "new", "due", "wrong", "all"],
        help="วิธีเลือกข้อ (ค่าเริ่มต้น mixed)",
    )
    s.add_argument("--auto", action="store_true", help="แสดงข้อ+เฉลย ไม่ต้องตอบ ไม่บันทึกสถิติ")
    s.add_argument("--seed", type=int, help="ล็อกการสุ่ม (ใช้เทส)")
    s.add_argument("--notify", action="store_true", help="ส่งผลเข้า Telegram")
    s.set_defaults(func=cmd_quiz)

    s = sub.add_parser("score", help="กรอก/คำนวณคะแนนรวม กสพท")
    s.add_argument("--set", action="append", metavar="วิชา=คะแนน", help="เช่น --set bio=72")
    s.add_argument("--from-mastery", action="store_true", help="ประมาณคะแนนจากผล quiz")
    s.add_argument("--target", type=float, help="คะแนนเป้าหมาย เพื่อดูว่าต้องทำอีกเท่าไร")
    s.set_defaults(func=cmd_score)

    s = sub.add_parser("rank", help="จัดอันดับคณะและประเมินโอกาส")
    s.add_argument("--score", type=float, help="คะแนนรวม กสพท ที่ใช้เทียบ")
    s.add_argument("--from-mastery", action="store_true", help="ใช้คะแนนที่ประมาณจากผล quiz")
    s.add_argument("--faculty", help="กรองเฉพาะคณะนี้ เช่น แพทยศาสตร์")
    s.add_argument("--limit", type=int, default=20, help="แสดงกี่คณะ")
    s.add_argument("--programs", help="ไฟล์คณะ (ค่าเริ่มต้น config/tcas_programs.yaml)")
    s.set_defaults(func=cmd_rank)

    s = sub.add_parser("progress", help="ความคืบหน้ารายวิชา + สถิติ quiz")
    s.set_defaults(func=cmd_progress)

    s = sub.add_parser("tests", help="ตารางทดสอบ (รายสัปดาห์ / รายเดือน / สอบเสมือนจริง)")
    s.add_argument(
        "--kind", choices=["weekly", "monthly", "mock"], help="กรองเฉพาะประเภทนี้"
    )
    s.add_argument("--limit", type=int, default=15, help="แสดงกี่รายการ")
    s.set_defaults(func=cmd_tests)

    s = sub.add_parser("export", help="สร้างเว็บแอป (PWA) ติดตั้งลงหน้าจอโฮมได้")
    s.add_argument(
        "--single", action="store_true",
        help="สร้างเป็นไฟล์ HTML ไฟล์เดียวแทน (ส่งต่อง่าย แต่ติดตั้งเป็นแอปไม่ได้)",
    )
    s.add_argument("--out", help="ปลายทาง (ค่าเริ่มต้น web/dist/ หรือ web/tcas_app.build.html)")
    s.add_argument("--template", help="ไฟล์ template (ค่าเริ่มต้น web/tcas_app.html)")
    s.add_argument("--programs", help="ไฟล์คณะ (ค่าเริ่มต้น config/tcas_programs.yaml)")
    s.add_argument("--resources", help="ไฟล์แหล่งเรียนรู้ (ค่าเริ่มต้น config/tcas_resources.yaml)")
    s.set_defaults(func=cmd_export)

    s = sub.add_parser("cutoff", help="กรอกคะแนนต่ำสุดของคณะ (แทนการแก้ YAML เอง)")
    s.add_argument("code", nargs="?", help="รหัสคณะ เช่น tu_dent")
    s.add_argument("pairs", nargs="*", help="ปี=คะแนน เช่น 2568=70.4 2569=70.6")
    s.add_argument("--list", nargs="?", const="", metavar="คณะ",
                   help="ดูรายการรหัสคณะ (กรองด้วยชื่อกลุ่มคณะได้)")
    s.add_argument("--unverified", action="store_true",
                   help="บันทึกแต่ยังไม่ตั้ง verified: true")
    s.set_defaults(func=cmd_cutoff)

    s = sub.add_parser("verify", help="ไล่ตัวเลขที่ยังไม่ยืนยันกับประกาศจริง")
    s.add_argument("--strict", action="store_true",
                   help="ออกด้วย exit 1 ถ้ายังเหลือระดับ 'ห้ามปล่อยผ่าน' (ใช้ใน CI)")
    s.set_defaults(func=cmd_verify)

    s = sub.add_parser("notify", help="ส่งสรุปประจำวันเข้า Telegram")
    s.add_argument("--test", action="store_true", help="ส่งข้อความทดสอบการเชื่อมต่อ")
    s.add_argument("--no-coverage", action="store_true", help="ไม่ต้องแนบความคืบหน้ารายวิชา")
    s.set_defaults(func=cmd_notify)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (KeyError, FileNotFoundError) as exc:
        print(f"ผิดพลาด: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
