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

## 7 ชีตในไฟล์เดียว

| ชีต | ดูอะไร |
|---|---|
| **Records** | ทุกรายงาน 1 บรรทัด (audit trail) + Sender + สาเหตุ + warning |
| **Daily Yield** | matrix วัน × เครื่อง (+ คอลัมน์รวม) — ดูทุกเครื่องพร้อมกัน |
| **Weekly Yield** | matrix สัปดาห์ × เครื่อง (+ รวม) |
| **Issue Log** | time-series เฉพาะรายงานที่มี fail (รู้ว่าเหตุเกิดเมื่อไร) + คอลัมน์ **Action / Status** ให้กรอกเอง |
| **By Shift** | เทียบ yield กะ Day vs Night |
| **By Operator** | yield / จำนวนรายงาน รายคน (เรียงตามปริมาณงาน) |
| **Fail Causes** | สาเหตุ fail ที่พบบ่อย (จับจากโน้ต เช่น OT/สลับเบรค, กาวไหลช้า, ซ่อมเครื่อง) + Fail units รวม |

### Issue Log + Action (สำคัญ)
คอลัมน์ **Action** (สิ่งที่ทำไปแก้) และ **Status** (Open/In progress/Done/Ignore — มี dropdown)
เป็นช่องให้คุณกรอกเอง ระบบ **ไม่ลบทิ้งตอนสร้างไฟล์ใหม่** — จับคู่ด้วย key ที่ซ่อนไว้
(`วันที่|เครื่อง|กะ|hash`) แล้วเติมกลับให้อัตโนมัติทุกครั้งที่ run ใหม่

## เอาขึ้น Google Sheets (ดูผ่าน network บริษัท + กรอก Action ได้)

ให้ Google Sheets เป็น "ตัวหลัก": ทีมเปิดดู/กรอก Action บน Sheets ผ่านเน็ตบริษัท
ส่วนสคริปต์รันสิ้นวันแล้ว **push ทับเฉพาะข้อมูลที่คำนวณ แต่ดึง Action/Status ที่กรอก
ไว้กลับมาก่อน** จึงไม่ทับของที่พิมพ์ไป

ตั้งค่าครั้งเดียว:
1. สร้าง Google Service Account (Google Cloud Console) → ดาวน์โหลด JSON key เป็น `service_account.json`
2. เปิด Google Sheet ใหม่ → Share อีเมลของ service account (ใน JSON) แบบ **Editor**
3. `pip install gspread`
4. รันสิ้นวัน:
```bash
python ops_yield_cli.py --line-export chat.txt \
    --out yield.xlsx \
    --gsheet-url "https://docs.google.com/spreadsheets/d/XXXX/edit" \
    --gsheet-creds service_account.json
```
ทีมที่ทำงานเปิด URL นี้ดู Daily/Weekly/Issue Log ได้เลย และพิมพ์ Action ลงไปได้

## รูปแบบข้อความที่รองรับ

เรียนรู้จาก LINE export จริง (กลุ่ม Super Underfill ปี 2022–2026) format ปัจจุบัน:

```
@NapatB. เครื่องAUTO Underfill #(5)
Run ได้ปกติครับ
Jun 17 2026 Day
✅Run 79 Unit
✅ไม่มี Fail L1
❌มี Fail L2  2 Unit
✅ไม่มี Splash
```

parser จับ field พวกนี้และทนต่อความหลากหลายจริงที่เจอในข้อมูล:
- หมายเลขเครื่อง: `#(5)` / `# (1)` / `Manual# 2` / `(7)` หรือ**ข้อความไทย** `#(เคาท์ดาวน์)`
- Mode `Manual` หรือ `AUTO` (มักติดกับไทย `เครื่องAUTO`)
- จำนวนผลิต `✅Run 79 Unit` (ยึดกับคำว่า Run)
- Fail L1 / Fail L2 / Splash — **ตัวเลขอยู่หลัง label**: `มี Fail L1 1 Unit`→1,
  `ไม่มี ...`→0, label ที่ไม่มีในข้อความ→0, label เว้นวรรค `Fail L 2` ก็จับได้
- ดักกับดัก `(ไม่มีทาง)มี Fail L1 1 Unit` → ได้ 1 (ตัวเลขชนะคำว่า "ไม่มี")

**ความแม่นยำบนข้อมูลจริงปี 2026: parse สะอาด 98%** (1852/1888 รายงาน) ที่เหลือ 36
รายงานถูก flag ไว้ให้ตรวจเอง เพราะกำกวมจริง เช่นเขียน `✅มี splash` ไม่ใส่จำนวน หรือ
ใส่ `(เคาท์ดาวน์)` ตรงที่ควรเป็นตัวเลข — ระบบไม่เดามั่ว

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
# เรียนรู้/สร้างย้อนหลังจากไฟล์ LINE export (Save chat history) ทั้งไฟล์
python ops_yield_cli.py --line-export chat.txt --out yield.xlsx
python ops_yield_cli.py --line-export chat.txt --year 2026 --out yield.xlsx

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
| `lineexport.py` | อ่านไฟล์ LINE export `.txt` → แยกข้อความ multi-line → `Record` |
| `analysis.py` | aggregate รายกะ / รายคน / สาเหตุ fail (taxonomy เรียนจากข้อมูลจริง) |
| `to_gsheet.py` | push ทุกชีตขึ้น Google Sheets ผ่าน gspread (คง Action/Status ที่กรอก) |
| `workbook.py` | เขียน/อัปเดต `.xlsx` 3 ชีต: Records, Daily Yield, Weekly Yield |
| `collector.gs` | Google Apps Script รับ webhook จาก LINE → เก็บลง Sheet |
| `../ops_yield_cli.py` | CLI รวบข้อความทั้งวัน → workbook |
| `sample_messages.txt` | ข้อความตัวอย่างไว้ทดสอบ |
