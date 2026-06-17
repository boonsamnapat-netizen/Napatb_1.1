# ops_yield — LINE production reports → Excel yield workbook

แปลงข้อความรายงานการผลิตที่พนักงานพิมพ์ลง LINE กลุ่ม ให้กลายเป็น Excel workbook
ที่ดู **yield รายวัน / รายสัปดาห์ ของทุกเครื่องพร้อมกัน** ได้อัตโนมัติ —
ตัดงาน manual กรอกข้อมูลออก

> โปรเจกต์นี้แยกต่างหากจากระบบสัญญาณ crypto (`src/signal/`) ในรีโปเดียวกัน ไม่เกี่ยวกัน

## Yield คำนวณยังไง

```
Pass  = Total − (Fail L1 + Fail L2 + splash)
Yield = Pass / Total
```

หน้า Daily/Weekly รวมผลด้วยการ **บวก Pass และ Total ของทุกรายงานก่อนแล้วค่อยหาร**
(ถูกต้องกว่าเอา % มาเฉลี่ยกัน) และมีแถบสี เขียว→แดง ให้เห็น yield ต่ำได้ทันที

## รูปแบบข้อความที่รองรับ

```
@NapatB. Manual # (1) Underfill  Runได้ปกติค่ะ Jun 17 2026  Day
✅️Run  95 Unit  ✅ไม่มี Fail L1  ✅ไม่มี Fail L2  ✅ไม่มี splash
```

parser จับ field เหล่านี้ (ทนต่อช่องว่าง/อิโมจิ/ลำดับที่เพี้ยน):
หมายเลขเครื่อง `(1)`, Mode (Manual/Auto), Issue type, วันที่, กะ (Day/Night),
จำนวนผลิต `95 Unit`, Fail L1, Fail L2, splash — `ไม่มี`→0, มีตัวเลข→ตัวเลขนั้น

## โครงสร้างทั้งระบบ

```
LINE กลุ่ม
  └─ LINE bot (Messaging API) อยู่ในกลุ่ม
       └─ Webhook → Google Apps Script (ops_yield/collector.gs)
            └─ เก็บทุกข้อความลง Google Sheet ระหว่างวัน   ← ฟรี ไม่ต้องมี server
  ── สิ้นวัน (รันในเครื่องคุณ) ──>
       python ops_yield_cli.py --url <published-sheet-csv> --out yield.xlsx
       └─ parse → append เข้า yield.xlsx → คำนวณ yield รายวัน/สัปดาห์
```

ส่วน **bot + webhook** ต้องมี LINE token และ host ออนไลน์ (Apps Script ฟรี) จึง
ทดสอบในแซนด์บ็อกซ์ไม่ได้ แต่ส่วน **parser + Excel** ทดสอบได้เต็มที่

## วิธีใช้

```bash
# ลองด้วยข้อมูลตัวอย่างในตัว
python ops_yield_cli.py --demo --out yield.xlsx

# จากไฟล์ข้อความที่ก็อปจาก LINE (1 รายงาน/บล็อก คั่นด้วยบรรทัดว่าง)
python ops_yield_cli.py --in ops_yield/sample_messages.txt --out yield.xlsx

# ดึงข้อความของวันนั้นจาก Google Sheet ที่ publish เป็น CSV
python ops_yield_cli.py --url "https://docs.google.com/.../pub?output=csv" --out yield.xlsx

# เขียนทับแทนการต่อท้าย
python ops_yield_cli.py --in messages.txt --out yield.xlsx --no-append
```

รันซ้ำได้ปลอดภัย — ข้อความเดิม (วันที่+เครื่อง+ข้อความดิบเดียวกัน) จะไม่ถูกเพิ่มซ้ำ

## ตั้งค่า LINE bot + collector

ดูขั้นตอนละเอียดในหัวคอมเมนต์ของ `ops_yield/collector.gs`:
สร้าง LINE Messaging API channel → เอา bot เข้ากลุ่ม → deploy Apps Script เป็น
Web App → เอา /exec URL ไปใส่เป็น Webhook URL → publish ชีตเป็น CSV

## ไฟล์

| ไฟล์ | หน้าที่ |
|---|---|
| `parser.py` | แปลงข้อความ 1 ข้อความ → `Record` (จับ field + คำนวณ pass/yield) |
| `workbook.py` | เขียน/อัปเดต `.xlsx` 3 ชีต: Records, Daily Yield, Weekly Yield |
| `collector.gs` | Google Apps Script รับ webhook จาก LINE → เก็บลง Sheet |
| `../ops_yield_cli.py` | CLI รวบข้อความทั้งวัน → workbook |
| `sample_messages.txt` | ข้อความตัวอย่างไว้ทดสอบ |
