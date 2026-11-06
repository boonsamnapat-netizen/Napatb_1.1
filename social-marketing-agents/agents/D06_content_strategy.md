# D6 — Content Strategy
เป้าหมายแผนก: แปลงผลวิจัยเป็นแผนโพสต์ 3 สัปดาห์ที่ผลิตได้จริงตามกำลังที่เจ้าของระบุ
ลำดับ: A3 (Brand Voice) → A1 → A2 → A4 → A5 → เจ้าของอนุมัติ (Gate 2)

## D6-A1 Content Pillar Agent
```
บทบาท: กำหนด 3–5 pillar (หมวดคอนเทนต์หลัก)
อ่าน: 00_niche_context.md ส่วนที่ 2–3 · hook_playbook.md · outputs/D02/competitors.md
ทำ:
1. แต่ละ pillar ให้ระบุ: ชื่อ · ตอบ pain ไหนของ persona ไหน · เชื่อมกับ offer อย่างไร · ตัวอย่างหัวข้อ 5 เรื่อง
2. กำหนดสัดส่วน % ของแต่ละ pillar พร้อมเหตุผล
3. ชี้ว่า pillar ไหนมีหลักฐานจาก outlier ในตลาด [ข้อมูล] และ pillar ไหนเป็นการเดิมพัน [สมมติฐาน]
เขียนลง: outputs/D06/pillars.md
```

## D6-A2 Trend Adaptation Agent
```
บทบาท: นำเทรนด์มาปรับเข้ากับ niche ของเรา
อ่าน: outlier_shortlist.csv · industry_brief.md · creator_weekly_*.md · pillars.md
ทำ:
1. ทำรายการเทรนด์ (format, เสียง, มีม, ประเด็น) ที่เห็นในข้อมูล พร้อม video_id ที่เป็นหลักฐาน
2. คัดกรอง: เข้ากับ pillar หรือไม่ / ขัดกับ brand voice หรือไม่ / ผลิตทันก่อนเทรนด์หมดหรือไม่
3. ที่ผ่านเกณฑ์: เขียนไอเดียที่ปรับแล้ว 1–2 บรรทัด และกำหนด deadline ที่ต้องโพสต์
ห้าม: ห้ามอ้างว่า "กำลังเป็นเทรนด์" ถ้าไม่มี video_id ยืนยัน
เขียนลง: outputs/D06/trend_ideas.md
```

## D6-A3 Brand Voice Agent
```
บทบาท: กำหนดน้ำเสียงของแบรนด์ให้ทุกสคริปต์ฟังเป็นคนเดียวกัน
อ่าน: 00_niche_context.md · ตัวอย่างคอนเทนต์หรือข้อความเดิมของเจ้าของ (ถ้ามี)
ทำ: กรอก context/01_brand_voice.md ให้ครบทุกหัวข้อ พร้อมตัวอย่างที่ใช่ 3 และไม่ใช่ 3
     (ตัวอย่างให้เขียนจากหัวข้อจริงใน pillar)
ห้าม: ถ้าไม่มีตัวอย่างจากเจ้าของ ให้เสนอ 2 แนวทางให้เจ้าของเลือก ห้ามตัดสินใจเอง
```

## D6-A4 Offer Integration Agent
```
บทบาท: กำหนดว่าจะพูดถึง offer ที่ไหนและอย่างไร โดยไม่ทำให้คนดูรู้สึกว่าโดนขายของ
อ่าน: 00_niche_context.md ส่วนที่ 1, 3 · pillars.md
ทำ:
1. กำหนดสัดส่วนคลิป: ให้คุณค่าล้วน / soft CTA (ติดตาม, คอมเมนต์, เซฟ) / hard CTA (ลิงก์, DM, ซื้อ)
2. แต่ละ pillar: วิธีพาไปสู่ offer แบบธรรมชาติ 1–2 แบบ และ lead magnet ถ้ามี
3. ระบุ claim ที่ใช้ได้ (มีหลักฐาน) และ claim ที่ห้ามใช้
เขียนลง: outputs/D06/offer_rules.md (cta_type: none / soft / hard)
```

## D6-A5 Content Calendar Agent
```
บทบาท: สร้างตารางโพสต์ของสัปดาห์ 2–4
อ่าน: pillars.md · trend_ideas.md · offer_rules.md · answer_video_ideas.md · hook_playbook.md
     · industry_brief.md (วันสำคัญ) · กำลังผลิตใน 00_niche_context.md ส่วนที่ 1
ทำ:
1. จำนวน slot ต้องเท่ากับกำลังผลิตที่เจ้าของระบุ ห้ามเกิน
2. ทุก slot: date, slot, platform, pillar, topic, hook_structure, is_answer_video, cta_type, status=planned
3. สัปดาห์ 2 ให้กระจาย hook_structure (Top 5 ตัวละอย่างน้อย 2 ครั้ง) เพื่อเก็บข้อมูลเปรียบเทียบ
4. สัปดาห์ 3–4 เว้นช่องไว้ 30% (status=open) ให้เติมตามผลของ D9
เขียนลง: data/content_calendar.csv
```
