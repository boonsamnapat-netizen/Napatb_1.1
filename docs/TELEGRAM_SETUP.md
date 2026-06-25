# วิธีตั้งค่า Telegram Alert (ละเอียดทุกขั้นตอน)

ทำครั้งเดียว ใช้ได้ตลอด — ระบบจะยิง signal ตอน decision=ENTER เข้ามือถือคุณ

---

## ขั้นที่ 1 — สร้างบอท แล้วเอา TOKEN

1. เปิด Telegram ค้นหา **@BotFather** (มีเครื่องหมายติ๊กฟ้า) แล้วกด Start
2. พิมพ์ `/newbot` แล้วส่ง
3. BotFather ถามชื่อบอท (ตั้งอะไรก็ได้) เช่น `My Crypto Signal`
4. ถามต่อ **username** ของบอท — ต้องลงท้ายด้วย `bot` เช่น `napat_signal_bot`
5. สำเร็จ! BotFather จะส่ง **token** หน้าตาแบบนี้:
   ```
   8123456789:AAH9xT2k...ZsQ1aBcDeFgHiJ
   ```
   ➡️ **เก็บ token นี้ไว้** (นี่คือ `TELEGRAM_BOT_TOKEN`)

> ⚠️ อย่าเปิดเผย token ให้ใคร ใครมี token = ควบคุมบอทคุณได้

---

## ขั้นที่ 2 — เอา CHAT ID (ปลายทางที่จะส่งหา)

**สำคัญ: ต้องกด Start บอทตัวเองก่อน** ไม่งั้นบอทส่งหาคุณไม่ได้

1. ค้นหา username บอทที่เพิ่งสร้าง (เช่น `@napat_signal_bot`) → กด **Start** → พิมพ์ทักอะไรก็ได้ เช่น `hi`
2. เอา chat id ด้วยวิธีใดวิธีหนึ่ง:

   **วิธี A (ง่ายสุด):** ค้นหา **@userinfobot** ใน Telegram กด Start → มันจะบอก `Id: 123456789`
   ➡️ เลขนั้นคือ `TELEGRAM_CHAT_ID`

   **วิธี B (ผ่าน API):** เปิดลิงก์นี้ในเบราว์เซอร์ (แทน `<TOKEN>` ด้วย token จริง)
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
   หาคำว่า `"chat":{"id":123456789` — เลขนั้นคือ chat id
   (ถ้าว่างเปล่า ให้ไปทักบอทก่อนแล้วรีเฟรช)

---

## ขั้นที่ 3 — ทดสอบว่าส่งได้จริง (30 วินาที)

วางลิงก์นี้ในเบราว์เซอร์ (ใส่ token + chat id จริง):
```
https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<CHAT_ID>&text=ทดสอบ
```
ถ้ามีข้อความ "ทดสอบ" เด้งเข้า Telegram = **พร้อมแล้ว** ✅
ถ้าได้ error:
- `chat not found` → ยังไม่ได้กด Start บอท (ย้อนไปขั้น 2 ข้อ 1)
- `Unauthorized` → token ผิด

---

## ขั้นที่ 4A — เปิดใช้แบบอัตโนมัติ (รันเองบน GitHub ทุกวัน)

1. ไปที่ repo บน GitHub → **Settings** → **Secrets and variables** → **Actions**
2. กด **New repository secret** เพิ่ม 2 ตัว:
   | Name | Secret |
   |---|---|
   | `TELEGRAM_BOT_TOKEN` | token จากขั้น 1 |
   | `TELEGRAM_CHAT_ID` | chat id จากขั้น 2 |
3. เสร็จ! workflow **Auto Scan & Telegram Alert** จะรันเองทุกวัน 01:00 UTC (08:00 ไทย)
   แล้วยิงเฉพาะตอนมี ENTER เข้ามือถือคุณ

**อยากทดสอบทันทีโดยไม่รอ:** repo → แท็บ **Actions** → เลือก *Auto Scan & Telegram Alert*
→ **Run workflow** → ดู log ขั้น "Scan and alert"

---

## ขั้นที่ 4B — รันเองบนเครื่อง (อยากคุมเอง / เทรดสด)

```bash
export TELEGRAM_BOT_TOKEN="8123456789:AAH9..."
export TELEGRAM_CHAT_ID="123456789"

# ทดสอบยิงทันที (--notify-all บังคับส่งแม้ไม่ใช่ ENTER)
python signal_cli.py BTCUSDT --demo --no-news --notify --notify-all

# ใช้งานจริง: เช็กเหรียญเดียว ยิงเฉพาะตอน ENTER
python signal_cli.py BTCUSDT --tf 4h --htf 1d --notify

# สแกนทั้งตลาด + portfolio แล้วยิงตอนมี ENTER
python signal_scan.py --csv-dir data/real/crypto --htf W --account 1000 --portfolio --notify
```

ให้รันสด ต่อเนื่อง: ตั้ง cron บนเครื่อง/VPS เช่น ทุก 4 ชั่วโมง
```cron
0 */4 * * *  cd /path/to/Napatb_1.1 && python signal_scan.py --csv-dir data/real/crypto_1h --htf 4h --portfolio --notify >> scan.log 2>&1
```

---

## ปรับแต่ง

| อยากทำ | ทำที่ไหน |
|---|---|
| เปลี่ยนเวลายิง | `.github/workflows/auto_scan_alert.yml` → `cron` |
| เปลี่ยนรายชื่อเหรียญ | `data/crypto_universe.txt` |
| เปลี่ยนขนาดพอร์ต/ความเสี่ยง | `config/config.yaml` → `signal.portfolio` |
| ยิงทุก decision (ไม่เฉพาะ ENTER) | `signal_cli.py ... --notify --notify-all` |

---

## คำสั่งที่พิมพ์หาบอทได้ (อัปเดตข้อมูลผ่าน Telegram)

บอทจะอ่านข้อความเหล่านี้ตอน workflow รันรอบถัดไป (วันละครั้ง) แล้วบันทึกให้
พร้อมตอบยืนยันกลับ — สัญลักษณ์เหรียญพิมพ์สั้นได้ (ใส่/ไม่ใส่ USDT ก็ได้):

| อยากทำ | พิมพ์ว่า | ผลลัพธ์ |
|---|---|---|
| อัปเดตมูลค่าพอร์ต | `/port 150` (หรือ `พอร์ต 150`) | เขียน `data/account.json` → ใช้คำนวณ size |
| เปิดไม้ (จดลง journal) | `/trade AVAX short 6.19 6.804 5.50` | `SYMBOL ทิศ ENTRY SL [TP]` (ใช้ `เปิด` แทนก็ได้) |
| ปิดไม้ + คิด R ให้ | `/close AVAX 6.40` | ปิดไม้ล่าสุดของเหรียญนั้น คำนวณ R จาก entry/SL ที่จดไว้ |
| ดูสถิติ journal | `/journal` (หรือ `/stats`) | ตอบกลับ: จำนวนไม้, win rate, รวม R, เฉลี่ย R/ไม้, ไม้ที่ถืออยู่ |

- ทิศทาง: `long`/`buy`/`ลอง`/`ซื้อ` หรือ `short`/`sell`/`ช็อต`/`ขาย`
- ข้อมูลเก็บใน `data/trade_journal.json` (workflow commit ให้อัตโนมัติ) — แต่ละข้อความบันทึกครั้งเดียว ไม่ซ้ำ
- ปิดไม้คำนวณ R = ระยะที่ราคาวิ่งเข้าทาง ÷ ระยะ entry→SL (1R) ให้เอง

---

## แก้ปัญหาที่เจอบ่อย

| อาการ | สาเหตุ/วิธีแก้ |
|---|---|
| ไม่มีข้อความเด้ง แต่ workflow สำเร็จ | ตอนนั้นไม่มี ENTER (ระบบเงียบโดยตั้งใจ) — ลองทดสอบขั้น 3 หรือ `--notify-all` |
| `chat not found` | ยังไม่ได้กด Start บอท |
| `Unauthorized` / 401 | token ผิดหรือมีช่องว่างเกิน |
| ส่งเข้ากลุ่ม/แชนแนล | เพิ่มบอทเข้ากลุ่มก่อน, chat id ของกลุ่มจะขึ้นต้นด้วย `-` (เช่น `-100123...`) |
| dry-run ขึ้นใน log | ยังไม่ได้ตั้ง secrets/env — ใส่ให้ครบ |

> ⚠️ Alert เป็นเครื่องมือช่วยตัดสินใจ ไม่ใช่คำสั่งซื้อขายอัตโนมัติ — ตรวจสอบและบริหารความเสี่ยงเองทุกครั้ง
