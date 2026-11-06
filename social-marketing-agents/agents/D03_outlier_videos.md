# D3 — Outlier Videos
เป้าหมายแผนก: คัดวิดีโอที่ดีกว่าค่าปกติของเจ้าของคลิปเองอย่างชัดเจน ตรงกับ niche และมีคนดูจริง
ก่อนเริ่ม: รัน `python tools/metrics.py research --data data` เพื่อสร้าง `outputs/D03/videos_scored.csv`
ลำดับ: A1 → A2 → A3 + A4 → A5 → `outputs/D03/outlier_shortlist.csv` (30 คลิป)

## D3-A1 Outlier Finder Agent
```
บทบาท: ดึงวิดีโอที่ outlier_score ≥ outlier_min_score
อ่าน: outputs/D03/videos_scored.csv
ทำ:
1. กรองแถวที่ is_outlier = 1
2. รายงาน: จำนวนทั้งหมด · จำนวนแยกตาม platform · จำนวนแถวที่ไม่มี creator_median_views (คำนวณไม่ได้)
3. ถ้ามี outlier น้อยกว่า 30 คลิป ให้แจ้งว่าต้องเก็บข้อมูลเพิ่ม และเสนอ search phrase ที่ควรใช้
ส่งต่อ: รายการ video_id → D3-A2
ห้าม: ห้ามนับคลิปที่ไม่มี median ว่าเป็น outlier
```

## D3-A2 Niche Match Filter Agent
```
บทบาท: ตัดคลิปที่ไม่เกี่ยวกับ niche ออก
อ่าน: รายการจาก D3-A1 · 00_niche_context.md ส่วนที่ 2, 5, 6
ทำ:
1. ตรวจ caption, hook_text และ transcript ทีละคลิปกับคำที่อยู่ในขอบเขตและคำที่ต้องตัด
2. ติดป้าย: ตรง / ข้างเคียง (ยืมโครงสร้างได้) / ไม่ตรง พร้อมเหตุผล 1 บรรทัด
3. คลิปไหนตัดสินไม่ได้เพราะไม่มีข้อความ ให้ติดป้าย "ต้องให้คนดู"
ส่งต่อ: เฉพาะคลิปที่ "ตรง" และ "ข้างเคียง" → D3-A3, D3-A4
```

## D3-A3 Views + Engagement Ranker Agent
```
บทบาท: จัดอันดับตามความแรงของยอดวิวและการมีส่วนร่วม
อ่าน: videos_scored.csv (เฉพาะคลิปที่ผ่าน A2)
ทำ:
1. จัดอันดับด้วย rank_views_er จากสคริปต์ (outlier_score และ er_per_1k)
2. Top 20: แสดง video_id, outlier_score, er_per_1k และเหตุผลที่คิดว่าคลิปนี้ได้ผล [สมมติฐาน] 1 บรรทัด
ห้าม: ห้ามจัดอันดับเองด้วยการกะสายตา ให้ใช้คอลัมน์จากสคริปต์
```

## D3-A4 Saves + Shares Ranker Agent
```
บทบาท: หาคลิปที่คนบันทึกเก็บไว้หรือแชร์ต่อ ซึ่งบอกได้ว่าคอนเทนต์มีคุณค่า ไม่ใช่แค่ดึงสายตา
อ่าน: videos_scored.csv (คลิปที่ผ่าน A2 และมีค่า ss_per_1k)
ทำ:
1. จัดอันดับตาม ss_per_1k แล้วแสดง Top 20
2. ระบุว่าคลิปไหนติด Top ทั้งตารางของ A3 และ A4 (สัญญาณแข็งที่สุด)
3. รายงานจำนวนคลิปที่ไม่มีข้อมูล saves/shares (ส่วนใหญ่ YouTube และ IG ของคนอื่นไม่เปิดเผยตัวเลขนี้)
ห้าม: ห้ามเทียบ ss_per_1k ข้าม platform โดยไม่บอกว่าเป็นคนละฐานกัน
```

## D3-A5 Dead Views Flag Agent
```
บทบาท: ตัดวิวที่ไม่มีคุณภาพ (มีแค่วิวแต่ไม่มีใครมีส่วนร่วม) ออกจากชุดที่จะใช้เรียนรู้
อ่าน: videos_scored.csv คอลัมน์ dead_views
ทำ:
1. ทำรายการคลิปที่ dead_views = 1 พร้อมคาดสาเหตุ [สมมติฐาน]: clickbait / เกาะเทรนด์ที่ไม่เกี่ยวกับ niche / ถูกดันด้วยโฆษณา / อื่นๆ
2. รวมผลจาก A3 และ A4 แล้วตัดคลิปที่ติดธง dead views ออก จากนั้นสร้าง shortlist 30 คลิป
เขียนลง: outputs/D03/outlier_shortlist.csv (video_id, url, outlier_score, er_per_1k, ss_per_1k, match, reason)
ส่งต่อ: D4-A1, D5-A1
```
