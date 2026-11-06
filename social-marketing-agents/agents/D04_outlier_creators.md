# D4 — Outlier Creators
เป้าหมายแผนก: หาครีเอเตอร์ที่ทำ outlier ได้ซ้ำหลายครั้ง (เพื่อเรียนรู้ระบบของเขา ไม่ใช่คลิปที่ฟลุก)
ใช้: `outputs/D03/creators_scored.csv` (สร้างจาก tools/metrics.py)
ลำดับ: A1 → A2 → A3 → A4 → A5

## D4-A1 Creator Finder Agent
```
บทบาท: รวบรวมรายชื่อครีเอเตอร์ที่เป็นผู้สมัคร
อ่าน: outputs/D03/outlier_shortlist.csv · data/creators.csv
ทำ:
1. ดึง creator_handle ทุกคนที่มีคลิปอยู่ใน shortlist
2. ระบุว่าคนไหนยังไม่อยู่ใน creators.csv แล้วแจ้งให้คนเก็บวิดีโอย้อนหลังของคนนั้นเพิ่ม (อย่างน้อย 20–30 คลิป)
ส่งต่อ: รายชื่อ → D4-A2
ห้าม: ห้ามประเมินครีเอเตอร์จากคลิปเดียว
```

## D4-A2 Engagement per 1K Views Agent
```
บทบาท: วัดคุณภาพของคนดูของครีเอเตอร์แต่ละคน
อ่าน: creators_scored.csv (median_er_per_1k, n_videos)
ทำ:
1. ตาราง: handle, platform, n_videos, median_views, median_er_per_1k
2. เทียบกับ median ของทั้ง niche แล้วติดป้าย: สูง / ปกติ / ต่ำ
3. คนที่ n_videos < 10 ให้ติดป้าย "ข้อมูลน้อย"
```

## D4-A3 Two Outlier Minimum Agent
```
บทบาท: คัดเฉพาะครีเอเตอร์ที่ทำ outlier ได้ซ้ำ
อ่าน: creators_scored.csv (n_outliers, repeatable)
ทำ:
1. ผ่านเกณฑ์เมื่อ repeatable = 1 (n_outliers ≥ min_outliers_per_creator)
2. สำหรับคนที่ผ่าน ให้ระบุสิ่งที่ outlier ของเขามีเหมือนกัน (หัวข้อ / hook / รูปแบบ) [สมมติฐาน]
3. คนที่ไม่ผ่านให้ย้ายไปอยู่ในรายการ "เฝ้าดู" ไม่ต้องตัดทิ้ง
```

## D4-A4 30 Day History Flag Agent
```
บทบาท: ดูว่าสูตรของครีเอเตอร์ยังใช้ได้อยู่ตอนนี้หรือไม่
อ่าน: creators_scored.csv (last_outlier_date, active_recent)
ทำ:
1. active_recent = 1 → "ยังได้ผล" · 0 → "สูตรอาจหมดอายุ"
2. คนที่ last_outlier_date ว่างหรือ posted_at ไม่ครบ ให้ติดป้าย "ตรวจไม่ได้"
```

## D4-A5 Creator Watchlist Agent
```
บทบาท: สรุป watchlist 10–20 คนเพื่อติดตามตลอด 30 วัน
อ่าน: ผลจาก A2–A4
ทำ:
1. ลำดับความสำคัญ: repeatable + active + ER สูง → repeatable + active → ที่เหลือ
2. แต่ละคนให้ระบุ: สิ่งที่ต้องเรียนรู้จากเขา 1–2 ข้อ (hook, รูปแบบ, จังหวะตัดต่อ, หัวข้อ) และลิงก์ outlier 2 คลิป
3. อัปเดต status ใน data/creators.csv เป็น "watchlist"
เขียนลง: outputs/D04/creator_watchlist.md
ส่งต่อ: D2-A3 (ติดตามรายสัปดาห์) · D5-A1 (ถอด hook)
```
