# โครงสร้างไฟล์กลาง (Shared Context)

กฎ: **ทุก Agent อ่าน `00_niche_context.md` ก่อนเสมอ** · แต่ละไฟล์มี "เจ้าของ" เขียนได้คนเดียว คนอื่นอ่านอย่างเดียว

```
marketing-os/
├── context/                      ← ความจำระยะยาว (markdown)
│   ├── 00_niche_context.md       ★ ทุก Agent อ่าน
│   ├── 01_brand_voice.md         ★ D6–D8 อ่าน
│   ├── 02_learnings.md           D9 เขียน · D5–D7, D10 อ่าน
│   ├── 03_error_log.md           D10 เขียน
│   ├── 04_prompt_changelog.md    D10 เขียน (ต้องให้คนอนุมัติ)
│   └── 05_playbook.md            D10 เขียน · ทุกแผนกอ่าน (pattern ที่ยืนยันแล้ว)
├── data/                         ← ตัวเลขดิบ (CSV) ห้ามแต่งเอง
│   ├── videos.csv                วิดีโอจากตลาด (คู่แข่ง/ครีเอเตอร์)
│   ├── creators.csv              ครีเอเตอร์ที่ติดตาม
│   ├── hook_bank.csv             hook ที่ถอดจากวิดีโอ
│   ├── content_calendar.csv      แผนโพสต์
│   └── performance_log.csv       ผลโพสต์ของเราเอง
├── outputs/D01 … D10/            ← งานของแต่ละแผนก
└── tools/metrics.py              ← คำนวณตัวเลข
```

## ใครอ่าน / เขียนอะไร

| ไฟล์ | เจ้าของ (เขียน) | ผู้อ่านหลัก |
|---|---|---|
| `00_niche_context.md` | D1 (A1, A2, A4, A5) · D2-A1 เติมส่วนคู่แข่ง | ทุกคน |
| `01_brand_voice.md` | D6-A3 | D6, D7, D8 |
| `02_learnings.md` | D9-A3 | D5-A5, D6, D7, D10 |
| `03_error_log.md` | D10-A1 | D10-A3, D10-A5 |
| `04_prompt_changelog.md` | D10-A3 | Orchestrator |
| `05_playbook.md` | D10-A2, D10-A4 | ทุกคน |
| `videos.csv` | คน/สคริปต์ดึงข้อมูล | D2–D5 |
| `creators.csv` | D2-A3, D4 | D2, D4 |
| `hook_bank.csv` | D5-A1, D5-A2 | D5, D7 |
| `content_calendar.csv` | D6-A5 | D7, D8, D9 |
| `performance_log.csv` | D9-A1 (จากข้อมูลจริง) | D9, D10 |

## Schema ของ CSV

| ไฟล์ | คอลัมน์ |
|---|---|
| `videos.csv` | `video_id, platform, url, creator_handle, posted_at, caption, hook_text, transcript, views, likes, comments, shares, saves, creator_median_views, source, collected_at` |
| `creators.csv` | `creator_handle, platform, followers, category, why_tracked, status, last_checked` |
| `hook_bank.csv` | `hook_id, video_id, hook_text, hook_source, structure, notes` |
| `content_calendar.csv` | `date, slot, platform, pillar, topic, hook_structure, is_answer_video, cta_type, script_id, status` |
| `performance_log.csv` | `post_id, script_id, platform, posted_at, snapshot_hours, views, likes, comments, shares, saves, avg_watch_s, completion_rate, follows, profile_visits, link_clicks, hook_structure, pillar, collected_at` |

- ช่องที่ไม่มีข้อมูลให้ **เว้นว่าง** ห้ามใส่ 0 เพราะ 0 แปลว่า "วัดแล้วได้ศูนย์"
- `source` = แหล่งข้อมูล เช่น `virlo`, `youtube_api`, `manual`
- `hook_source` = `transcript` / `onscreen_text` / `caption_only`

## นิยามตัวชี้วัด (ใช้ทุกแผนกเหมือนกัน)

| ตัวชี้วัด | สูตร | ใช้ที่ |
|---|---|---|
| Outlier score | `views ÷ median views ของครีเอเตอร์คนนั้น` | D3, D4 |
| ER/1K | `(likes+comments+shares+saves) ÷ views × 1000` (ใช้เฉพาะช่องที่มีข้อมูล) | D3, D4 |
| Saves+Shares/1K | `(saves+shares) ÷ views × 1000` | D3-A4 |
| Dead views | outlier แต่ ER/1K < 0.5 × median ER/1K ของทั้ง niche | D3-A5 |
| Repeatable creator | มี outlier ≥ 2 คลิปในชุดข้อมูล | D4-A3 |
| Active creator | มี outlier ภายใน 30 วันล่าสุด | D4-A4 |
| Winner / Loser (ของเรา) | views ที่ชั่วโมง X ÷ median ของโพสต์ก่อนหน้าที่ชั่วโมงเดียวกัน ≥ 1.5 / ≤ 0.5 | D9-A2 |

สูตร outlier score ตรงกับที่ Virlo ใช้ (views ÷ creator median) จึงนำค่าจาก Virlo มาใส่ช่อง `creator_median_views` ได้โดยตรง
