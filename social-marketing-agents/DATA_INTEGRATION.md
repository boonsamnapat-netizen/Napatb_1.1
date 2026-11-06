# การเชื่อมต่อข้อมูลจริง

ระบบนี้รับข้อมูลผ่าน CSV 2 ไฟล์ คือ `data/videos.csv` (ตลาด) และ `data/performance_log.csv` (บัญชีของเรา)
จะดึงข้อมูลมาจากแหล่งไหนก็ได้ ขอแค่จัดให้ตรง schema แล้ว Agent จะใช้งานได้เหมือนกัน

## สรุปว่าแต่ละแหล่งให้อะไรบ้าง

| แหล่ง | วิดีโอของคนอื่น | views | likes/comments | shares | saves | หมายเหตุ |
|---|---|---|---|---|---|---|
| **Virlo API** | ✅ TikTok / YT / IG | ✅ | ✅ | ไม่ระบุใน endpoint outlier | ไม่ระบุใน endpoint outlier | คำนวณ outlier score ให้เลย |
| **YouTube Data API v3** | ✅ | ✅ | ✅ | ❌ | ❌ | ฟรีภายใน quota |
| **Instagram Graph API** | จำกัด | ต้องตรวจ | ✅ (business_discovery) | ของเราเท่านั้น | ของเราเท่านั้น | ต้องเป็นบัญชี Business/Creator |
| **TikTok Display API** | ❌ (ของเราเท่านั้น) | ✅ | ✅ | ✅ | ต้องตรวจ | ต้องผ่าน app review |
| **TikTok Research API** | ✅ | ✅ | ✅ | ✅ | ต้องตรวจ | เปิดให้เฉพาะนักวิจัยที่ผ่านเงื่อนไข |
| **กรอกมือ / export จากแอป** | ✅ | ✅ | ✅ | ✅ (TikTok แสดงหน้าคลิป) | ✅ (TikTok แสดงหน้าคลิป) | ช้า แต่ใช้งานได้ทันที |

"ต้องตรวจ" หมายถึงยังไม่ได้ตรวจกับเอกสารล่าสุด ให้ทดลองเรียก API แล้วดู field ที่ได้กลับมาจริงก่อนใช้งาน

## 1. Virlo (เหมาะกับ D3–D4 มากที่สุด)
จากเอกสารของ Virlo ([dev.virlo.ai](https://dev.virlo.ai/docs/satellite/video-outlier)):
- Base URL: `https://api.virlo.ai/v1` · Auth: `Authorization: Bearer virlo_tkn_...`
- `POST /v1/satellite/video-outlier` body `{"url": "...", "platform": "tiktok|youtube|instagram"}`
  → ได้ `job_id` → ใช้ `GET /v1/satellite/video-outlier/status/:job_id` เพื่อรับผล
- ผลที่ได้: `analysis.outlier_score` (= views ÷ median views ของครีเอเตอร์), `analysis.median_views`,
  `analysis.performance_label` (mega_viral ≥ 10, viral 3–10, above_average 1.5–3), `result.video.views/likes/comments`
- ถ้า `analysis.videos_analyzed = 0` ห้ามใช้ score ของคลิปนั้น
- นอกจากนี้ยังมี endpoint สำหรับค้นหาด้วย keyword, creator lookup และ hashtag lookup (ดูรายละเอียดในเอกสาร)
- คิดค่าใช้จ่ายตามจำนวน request ไม่ต้องสมัครแพ็กเกจแอป · ราคาและ rate limit ให้ตรวจในหน้าเว็บของ Virlo

**การแมปเข้า videos.csv**: `views` ← result.video.views · `creator_median_views` ← analysis.median_views · `source` = virlo
(ใส่ median ของ Virlo แล้ว metrics.py จะคำนวณ outlier score ได้ตรงกับค่าของ Virlo)

ตัวอย่าง (Python):
```python
import os, time, requests
H = {"Authorization": f"Bearer {os.environ['VIRLO_API_KEY']}"}
job = requests.post("https://api.virlo.ai/v1/satellite/video-outlier", headers=H,
                    json={"url": VIDEO_URL, "platform": "tiktok"}).json()["data"]
# อ่านชื่อ field ของ job_id ใน response จริงก่อนใช้งาน
```

## 2. YouTube Data API v3 (ฟรี เหมาะกับ Shorts)
- `search.list` (q = search phrase, type=video, videoDuration=short) → ได้ video_id
- `videos.list?part=statistics,snippet` → viewCount, likeCount, commentCount, publishedAt
- `channels.list` + `playlistItems.list` (uploads playlist) → ใช้ดึงคลิปย้อนหลังของช่องเพื่อคำนวณ median
- `search.list` ใช้ quota เยอะกว่า `videos.list` มาก จึงควรค้นครั้งเดียวแล้วเก็บ video_id ไว้ใช้ต่อ

## 3. บัญชีของเราเอง (D9)
- **ง่ายที่สุด**: ดูตัวเลขใน TikTok Studio, Instagram Insights และ YouTube Studio ตามรอบ snapshot แล้วกรอกลง `performance_log.csv`
  (หรือส่งตัวเลขในแชตให้ Orchestrator แปลงเป็นแถว CSV)
- **อัตโนมัติ**: Instagram Graph API (insights ของ media) · YouTube Analytics API · TikTok Display API
  ทั้งหมดต้องใช้ OAuth กับบัญชีของคุณเอง

## 4. Scraper ของบุคคลที่สาม (เช่น Apify actors)
ใช้ได้ แต่ **อาจขัดกับข้อตกลงการใช้งาน (ToS) ของแพลตฟอร์ม** และชื่อ field เปลี่ยนได้ตลอด
ถ้าจะใช้ ให้แมปเข้า schema ก่อน และตรวจตัวเลขของ 5 คลิปแรกเทียบกับหน้าแอปจริง

## 5. อัปเกรดเป็นระบบอัตโนมัติ (เมื่อพร้อม)
```
Scheduler (cron / GitHub Actions รายวัน)
  → fetch_virlo.py / fetch_youtube.py  → data/videos.csv
  → fetch_own_stats.py                 → data/performance_log.csv
  → tools/metrics.py research|performance
  → เรียก LLM API ด้วย prompt ของ D9-A1…A4 (+ ไฟล์ context) → เขียน outputs/
  → ส่งสรุปเข้า Telegram/LINE/Slack
```
แนะนำให้ทำแบบกรอกมือให้ครบ 30 วันแรกก่อน แล้วค่อยเขียนโค้ดเฉพาะขั้นที่เสียเวลาที่สุด

## ข้อมูลขั้นต่ำที่ต้องมีก่อนเริ่มแต่ละแผนก
| แผนก | ขั้นต่ำ |
|---|---|
| D3 | ≥ 200 คลิปใน niche · มี `creator_median_views` หรือมีคลิปของครีเอเตอร์คนละ ≥ 5 คลิป |
| D4 | ครีเอเตอร์ใน shortlist มีคลิปย้อนหลังคนละ ≥ 20 คลิป |
| D5 | shortlist ≥ 30 คลิป และมี transcript หรือข้อความบนจอ |
| D9 | ตัวเลขของทุกโพสต์ที่ snapshot 48 ชม. |
