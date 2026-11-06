# Workflow 30 วัน

## หลักการ
- **ห้ามโพสต์ก่อนผ่าน Gate 1–2** (ถ้าไม่ได้ทำวิจัยก่อน ข้อมูลที่ได้กลับมาจะใช้เรียนรู้อะไรไม่ได้)
- เริ่มโพสต์ช่วงต้นสัปดาห์ 2 เพื่อให้มีเวลาเก็บข้อมูลของตัวเองอย่างน้อย 3 สัปดาห์
- ทุกแผนกส่งต่องานผ่านไฟล์เท่านั้น (ดู `CONTEXT_STRUCTURE.md`)

## สัปดาห์ 1 — Research (วันที่ 1–7)

| วัน | แผนก | งาน | ผลลัพธ์ |
|---|---|---|---|
| 1 | Orchestrator | `/kickoff` ถามข้อมูลเจ้าของ | niche_context ส่วนที่ 1 |
| 1–2 | D1 (A1→A5) | niche, persona, คู่แข่ง, search phrases, exclude | niche_context v1 |
| 2 | **คน** | ใช้ search phrases เก็บวิดีโอ ≥ 200 คลิป และ ≥ 20 ครีเอเตอร์ลง `videos.csv` | ข้อมูลดิบ |
| 2 | 🔒 **Gate 1** | เจ้าของอนุมัติ niche_context | — |
| 3–4 | D2 (A1→A5) | โปรไฟล์คู่แข่ง, อุตสาหกรรม, ครีเอเตอร์, Top companies, answer videos | outputs/D02 |
| 3–4 | D3 (A1→A5) | `metrics.py research` → outlier shortlist 30 คลิป | outlier_shortlist.csv |
| 5 | **คน** | เก็บวิดีโอย้อนหลังของครีเอเตอร์ที่ D4-A1 ขอเพิ่ม + transcript ของ shortlist | ข้อมูลเพิ่ม |
| 5–6 | D4 (A1→A5) | creator watchlist 10–20 คน | creator_watchlist.md |
| 6–7 | D5 (A1→A5) | hook bank → stats → hook playbook | hook_playbook.md |
| 7 | D10-A5 | audit สัปดาห์ 1 | audit_W1.md |

## สัปดาห์ 2 — Build + เริ่มโพสต์ (วันที่ 8–14)

| วัน | แผนก | งาน |
|---|---|---|
| 8 | D6 (A3→A1→A2→A4→A5) | brand voice, pillars, trends, offer rules, calendar สัปดาห์ 2–4 |
| 8 | 🔒 **Gate 2** | เจ้าของอนุมัติ brand voice และ calendar |
| 8–9 | D7 → D8 | สคริปต์และ production pack ของวันที่ 10–16 (ล่วงหน้า 1 สัปดาห์) |
| 9 | **คน** | ถ่ายทำแบบ batch |
| 10 | — | **เริ่มโพสต์** |
| 10–14 | Daily Loop | (ดูด้านล่าง) |
| 14 | D9-A5 · D10 (A2–A5) | รายงานสัปดาห์ · audit · เสนอการแก้ prompt |

สัปดาห์ 2 เน้น **กระจายตัวแปร** (hook structure, pillar, เวลาโพสต์) เพื่อหาว่าอะไรได้ผลกับบัญชีเรา

## สัปดาห์ 3 — Learn & Iterate (วันที่ 15–21)
- Daily loop ต่อเนื่อง
- D6-A5 เติม slot ที่ว่างไว้ 30% ตาม reco ของ D9-A4
- D5-A5 อัปเดต hook_playbook ด้วยผลของบัญชีเราเอง
- D2-A3 + D2-A5 รันรอบใหม่ (ครีเอเตอร์และ answer videos)
- วันที่ 21: รายงานสัปดาห์ + audit

## สัปดาห์ 4 — Double Down (วันที่ 22–30)
- 70% ของ slot ใช้ pattern ที่ "ยืนยัน" แล้ว · 30% ใช้ทดสอบใหม่
- ทำเวอร์ชันใหม่ของ winner (เนื้อหาเดิมแต่เปลี่ยน hook หรือเปลี่ยนมุม) แทนการโพสต์ซ้ำ
- วันที่ 28–30: D9-A5 ทำรายงานสรุป 30 วัน · D10-A4 ทำ playbook v1 สำหรับรอบถัดไป · D10-A5 ทำ audit รอบสุดท้าย

## Daily Loop (ตั้งแต่วันที่ 10)

```
เช้า   คน: ใส่ตัวเลขของโพสต์ที่ถึงเวลา snapshot (24/48/168 ชม.) → performance_log.csv
       python tools/metrics.py performance --data data --hours 48
       D9-A1 → D9-A2 → D9-A3 → D9-A4      (ได้ reco 3 ข้อ)
สาย    D6-A5 ปรับ calendar ตาม reco → D7 (A1→A5) เขียนสคริปต์ของ D+2 → D8 ทำ production pack
บ่าย   คน: ถ่าย / ตัดต่อ / โพสต์ตาม production pack
เย็น   D10-A1 บันทึก error ของวันนี้
```

## Feedback loop (ผลจริงย้อนกลับไปไหน)

| จาก | ไปที่ | เรื่อง |
|---|---|---|
| D9-A3 learnings | D5-A5 | ปรับอันดับโครงสร้าง hook |
| D9-A4 reco | D6-A5, D7 | ปรับแผนและสคริปต์ |
| D10-A2 playbook | ทุกแผนก | pattern ที่ยืนยันแล้ว / สิ่งที่ไม่ได้ผล |
| D10-A3 changelog | Orchestrator | prompt เวอร์ชันใหม่ (หลังคนอนุมัติ) |
