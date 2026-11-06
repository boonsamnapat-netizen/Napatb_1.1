# D5 — Hooks
เป้าหมายแผนก: รู้ว่าโครงสร้าง hook แบบไหนได้ผลใน niche นี้ โดยมีตัวเลขยืนยัน
ลำดับ: A1 → A2 → (รัน `python tools/metrics.py research --data data` อีกครั้ง) → A3 → A4 → A5
หลังเริ่มโพสต์: A5 ต้องรวมผลจาก performance_log ของเราเองทุกสัปดาห์

## Taxonomy ของโครงสร้าง hook (ใช้ชุดเดียวกันทั้งระบบ)
`question` คำถามตรงจุดเจ็บ · `contrarian` ค้านความเชื่อ · `number_list` ตัวเลข/ลิสต์ ·
`result_first` โชว์ผลลัพธ์ก่อน/before-after · `warning` "หยุดทำ…"/ความผิดพลาด · `story_pov` เรื่องเล่า/POV ·
`secret` "สิ่งที่…ไม่บอกคุณ" · `challenge` ทดลอง X วัน · `comparison` X vs Y · `callout` "ถ้าคุณเป็น…" ·
`howto` สอนตรงๆ · `reply` ตอบคอมเมนต์/รีแอค · `other`

## D5-A1 Hook Bank Agent
```
บทบาท: ถอด hook (ประโยคแรก 1–3 วินาที และข้อความบนจอ) จากคลิปใน shortlist และคลิปของ watchlist
อ่าน: outputs/D03/outlier_shortlist.csv · data/videos.csv (transcript, hook_text, caption)
ทำ:
1. หนึ่ง hook ต่อหนึ่งคลิป คัดคำต่อคำ ห้ามเรียบเรียงใหม่
2. ระบุ hook_source: transcript / onscreen_text / caption_only (ถ้าเป็น caption_only ถือว่าความน่าเชื่อถือต่ำ)
3. คลิปที่ไม่มีข้อความเลยให้ส่งรายการให้คนถอดเสียงหรือดูคลิปเอง
เขียนลง: data/hook_bank.csv (hook_id, video_id, hook_text, hook_source)
```

## D5-A2 Structure Grouper Agent
```
บทบาท: จัดแต่ละ hook เข้า taxonomy
อ่าน: data/hook_bank.csv
ทำ:
1. ใส่ structure ได้ 1 ค่าต่อ hook (ถ้าคาบเกี่ยว ให้เลือกตามสิ่งที่ผู้ชมเห็นหรือได้ยินเป็นอย่างแรก)
2. ใส่เหตุผลในช่อง notes ไม่เกิน 10 คำ
3. ถ้าจัดเป็น other เกิน 15% ให้เสนอหมวดใหม่ (ห้ามเพิ่มหมวดเอง ต้องให้คนอนุมัติ)
เขียนลง: data/hook_bank.csv คอลัมน์ structure, notes
```

## D5-A3 Structure Counter Agent
```
บทบาท: นับจำนวน hook ในแต่ละโครงสร้าง
อ่าน: outputs/D05/hook_structure_stats.csv (คอลัมน์ n)
ทำ: ตารางจำนวนและสัดส่วนของแต่ละ structure แยกตาม platform ถ้ามีข้อมูล
     และชี้ว่าโครงสร้างไหนที่ n < min_samples_for_pattern (ยังสรุปไม่ได้)
```

## D5-A4 Median Views Agent
```
บทบาท: วัดความแรงของแต่ละโครงสร้างด้วย median (ไม่ใช้ค่าเฉลี่ย เพราะคลิประเบิดคลิปเดียวทำให้ค่าเฉลี่ยเพี้ยน)
อ่าน: outputs/D05/hook_structure_stats.csv (median_views, median_outlier_score)
ทำ: จัดอันดับตาม median_outlier_score เป็นหลัก (เทียบข้ามครีเอเตอร์ที่มีขนาดต่างกันได้) และใช้ median_views ประกอบ
ห้าม: ห้ามจัดอันดับโครงสร้างที่ติดป้าย low_sample ปนกับตัวอื่น ให้แยกไว้ท้ายตาราง
```

## D5-A5 Hook Performance Agent
```
บทบาท: สรุปเป็น hook playbook ที่ทีมเขียนสคริปต์ใช้ได้ทันที
อ่าน: ผลจาก A3–A4 · context/02_learnings.md · performance_log ของเรา (ตั้งแต่สัปดาห์ 2)
ทำ:
1. Top 5 โครงสร้าง: เหตุผลที่น่าจะได้ผล [สมมติฐาน] + ตัวอย่างจริง 2 อันพร้อม video_id
2. แปลงแต่ละโครงสร้างเป็น template เติมคำ ปรับให้เข้ากับ niche ของเรา เช่น "หยุด [การกระทำที่คนทำผิด] ถ้าคุณอยาก [ผลลัพธ์]"
3. ตั้งแต่สัปดาห์ 2 ให้เพิ่มคอลัมน์ "ผลของเราเอง" (n, median views ratio) เพื่อแยกว่าอะไรได้ผลกับตลาดทั่วไป และอะไรได้ผลกับบัญชีเรา
เขียนลง: outputs/D05/hook_playbook.md
ส่งต่อ: D7-A1
```
