# Short-form Marketing OS — ทีม AI 50 Agents (10 แผนก × 5)

ระบบนี้คือทีม AI สำหรับทำ Short-form video บน TikTok, Instagram Reels และ YouTube Shorts ภายใน 30 วัน
ทุก Agent อ่านและเขียนลง **ไฟล์กลางชุดเดียวกัน** ไม่ส่งต่องานผ่านแชตลอย ๆ

## 1. ภาพรวมระบบ

```
                 ┌──────────────── ORCHESTRATOR (MASTER_PROMPT.md) ────────────────┐
                 │  สั่งงานตามลำดับวัน · ตรวจ gate · หยุดถามคนเมื่อข้อมูลไม่พอ         │
                 └─────────────────────────────────────────────────────────────────┘
   ข้อมูลจริง (Virlo / YouTube API / export จากแอป / กรอกมือ) → data/*.csv → tools/metrics.py
                                         │
 ┌──────────── สัปดาห์ 1: RESEARCH ─────────────┐   ┌──── สัปดาห์ 2: BUILD ────┐   ┌── สัปดาห์ 2–4: LOOP รายวัน ──┐
 │ D1 Niche → D2 Competitor → D3 Outlier Videos │ → │ D6 Strategy → D7 Script  │ → │ โพสต์ → D9 Performance       │
 │              → D4 Outlier Creators → D5 Hooks│   │        → D8 Production   │   │   ↺ ส่งผลกลับไป D5/D6/D7     │
 └──────────────────────────────────────────────┘   └──────────────────────────┘   └──────────────────────────────┘
                     D10 Memory & Improvement: บันทึก error · จำ pattern ที่ได้ผล · ปรับ prompt · audit ทุกสัปดาห์
```

| ชั้น | แผนก | ผลลัพธ์หลัก |
|---|---|---|
| วิจัย | D1 Niche Research | `context/00_niche_context.md` (ไฟล์ที่ทุกคนต้องอ่าน) |
| วิจัย | D2 Competitor Tracking | `outputs/D02/` + `data/creators.csv` |
| วิจัย | D3 Outlier Videos | `outputs/D03/outlier_shortlist.csv` |
| วิจัย | D4 Outlier Creators | `outputs/D04/creator_watchlist.md` |
| วิจัย | D5 Hooks | `data/hook_bank.csv` + `outputs/D05/hook_playbook.md` |
| ผลิต | D6 Content Strategy | `context/01_brand_voice.md` + `data/content_calendar.csv` |
| ผลิต | D7 Script Writing | `outputs/D07/scripts/*.md` |
| ผลิต | D8 Production Support | `outputs/D08/production_pack_*.md` |
| เรียนรู้ | D9 Performance Analysis | `data/performance_log.csv` + รายงาน |
| เรียนรู้ | D10 System Memory | `context/02–05_*.md` |

## 2. ไฟล์ในโฟลเดอร์นี้

| ไฟล์ | ใช้ทำอะไร |
|---|---|
| `MASTER_PROMPT.md` | **Prompt หลักสำหรับเริ่มระบบ** (คัดลอกไปวางได้ทันที) |
| `WORKFLOW_30_DAYS.md` | ลำดับงาน 4 สัปดาห์ + daily loop + gate |
| `CONTEXT_STRUCTURE.md` | โครงสร้างไฟล์กลาง, ใครอ่าน/เขียนไฟล์ไหน, schema ของ CSV, นิยามตัวชี้วัด |
| `agents/00_GLOBAL_RULES.md` | กฎที่แนบหน้า prompt ของทุก Agent |
| `agents/D01…D10_*.md` | System Prompt ของทั้ง 50 Agents |
| `context/*.md` | Template ของไฟล์กลาง |
| `data/*.csv` | Template ตารางข้อมูล (มีแค่หัวคอลัมน์) |
| `tools/metrics.py` | คำนวณ outlier score, ER/1K, dead views, median ของ hook, winner/loser |
| `DATA_INTEGRATION.md` | วิธีดึงข้อมูลจริง (Virlo, YouTube Data API, Instagram/TikTok API, กรอกมือ) |

## 3. วิธีเริ่มใช้งาน (สั้นที่สุด)

1. สร้าง Claude Project (หรือ AI ตัวอื่นที่แนบไฟล์ได้) แล้วอัปโหลดทั้งโฟลเดอร์นี้
2. วาง `MASTER_PROMPT.md` เป็น Project instructions
3. พิมพ์ `/kickoff` ระบบจะถามข้อมูลธุรกิจของคุณก่อน แล้วจึงเริ่ม D1
4. ใส่ข้อมูลวิดีโอจริงลง `data/videos.csv` (ดู `DATA_INTEGRATION.md`) แล้วรัน
   `python tools/metrics.py research --data data` ก่อนสั่ง D3–D5
5. หลังเริ่มโพสต์ ให้พิมพ์ `/day N` ทุกวัน

## 4. ข้อจำกัดที่ควรรู้ก่อนใช้

- **AI มองไม่เห็นยอดวิวเอง** Agent ใน D2–D5 และ D9 ทำงานได้จริงเมื่อคุณป้อนข้อมูลจริงเข้าไปเท่านั้น
  ถ้าไม่มีข้อมูล Agent ถูกตั้งให้ตอบว่า "ไม่มีข้อมูล" และห้ามเดาตัวเลข
- **ไม่ต้องรัน 50 แชตแยกกัน** ให้รันเป็นรายแผนก (10 ครั้ง) โดย Orchestrator สลับบทบาท 5 Agent ตามลำดับในแผนกเดียวกัน
  ถ้าต้องการ automation เต็มรูปแบบ ค่อยย้ายไปเขียนโค้ด (ดู `DATA_INTEGRATION.md` ข้อ 5)
- **การคำนวณให้สคริปต์ทำ** การจัดอันดับ, median และ ratio ให้ใช้ `tools/metrics.py` เพราะ LLM คำนวณตารางยาวผิดได้ง่าย
- เกณฑ์ตัวเลขทั้งหมด (outlier ≥ 3×, winner ≥ 1.5× ฯลฯ) เป็น **ค่าเริ่มต้นที่ผู้ออกแบบตั้งไว้ ไม่ใช่ค่าพิสูจน์แล้ว**
  ปรับได้ใน `context/00_niche_context.md` ส่วน Thresholds
- 30 วันเป็นเวลาสั้น ข้อสรุปจาก 1–2 โพสต์ยังไม่ใช่ pattern ระบบจึงบังคับให้มีจำนวนตัวอย่างขั้นต่ำก่อนสรุป
