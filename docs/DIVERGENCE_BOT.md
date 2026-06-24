# Divergence Signal Bot — Reference

บอทตรวจจับ **regular divergence** (RSI / MACD) พร้อมสถานะ overbought / oversold
แล้วสร้างแผนเทรดแบบคุมความเสี่ยง (Entry / SL / TP1-3 / RR) และยิงแจ้งเตือนภาษาไทย
เข้า Telegram

> ⚠️ เครื่องมือช่วยตัดสินใจ/เพื่อการศึกษา ไม่ใช่คำสั่งซื้อขายอัตโนมัติ — บริหารความเสี่ยงเองทุกครั้ง

---

## Divergence คืออะไร (ที่บอทนี้จับ)
- **Bullish divergent** — ราคาทำ *lower low* แต่ momentum (RSI/MACD) ทำ *higher low*
  → แรงขายอ่อนลง มีโอกาสกลับตัวขึ้น (มักมาคู่กับ **Oversold**)
- **Bearish divergent** — ราคาทำ *higher high* แต่ momentum ทำ *lower high*
  → แรงซื้ออ่อนลง มีโอกาสกลับตัวลง (มักมาคู่กับ **Overbought**)

จุด pivot ยืนยันด้วย fractal window (ค่า default 5 แท่ง) เพื่อกัน repaint บนแท่งที่ยังไม่ปิด

**สถานะ overbought / oversold**
- RSI: ≥70 = Overbought, ≤30 = Oversold
- MACD: ไม่มีกรอบตายตัว → ใช้ percentile ของ MACD line เทียบช่วง 100 แท่งล่าสุด
  (≥80th = Overbought, ≤20th = Oversold)

## รูปแบบข้อความที่ส่ง
```
🟢 เหรียญ BTC
Signal: Bullish divergent
Indicator status: MACD Oversold
Entry: 61250.0
SL: 59900.0
TP1: 62600.0
TP2: 63950.0
TP3: 65300.0
RR: 1:1.0 / 1:2.0 / 1:3.0
```
- **Entry** = ราคาปิดล่าสุด
- **SL** = เลย swing ของ divergence โดยเผื่อ ATR (มี floor 0.3% กัน stop แคบเกิน)
- **TP1/2/3** = Entry ± 1R / 2R / 3R (R = ระยะ Entry→SL)
- **RR** = reward:risk ของแต่ละ TP

## CLI — `signal_divergence.py`
```bash
# เหรียญเดียว (offline demo)
python signal_divergence.py BTCUSDT --demo

# เหรียญเดียวจาก CSV แล้วยิง Telegram
python signal_divergence.py BTCUSDT --csv data/real/crypto/BTCUSDT.csv --notify

# สแกนทั้งโฟลเดอร์ CSV + สรุป + ยิง
python signal_divergence.py --csv-dir data/real/crypto --notify --summary

# เลือก oscillator: auto (ค่าเริ่มต้น) | rsi | macd
python signal_divergence.py BTCUSDT --demo --indicator macd

# ดูตัวอย่างข้อความ (ไม่ต้องมีข้อมูล)
python signal_divergence.py --sample --notify
```
> sandbox ต่อ exchange ไม่ได้ → ใช้ `--csv*` หรือ `--demo`

## โครงสร้างโค้ด — `src/signal/`
| ไฟล์ | หน้าที่ |
|---|---|
| `indicators.py` | EMA / RSI / MACD / ATR |
| `market_data.py` | โหลด CSV + ตัวสร้างข้อมูล demo (offline) |
| `divergence.py` | หา pivot + ตรวจ regular divergence + สถานะ OB/OS |
| `signal_engine.py` | สร้างแผน Entry/SL/TP1-3/RR จาก divergence |
| `notifier.py` | จัดรูปข้อความไทย + ส่ง Telegram (dry-run ถ้าไม่มี secrets) |

ทดสอบ: `PYTHONPATH=. python tests/test_divergence.py`

## Deploy อัตโนมัติ
`.github/workflows/divergence_alert.yml` — รายวัน 01:00 UTC (08:00 ไทย):
fetch (yfinance) → scan divergence → ยิงไทยเข้า Telegram
- Secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (ดู `docs/TELEGRAM_SETUP.md`)
- Inputs: `indicator` (auto/rsi/macd), `sample` (ส่งตัวอย่าง)
- เหรียญที่สแกน: `data/crypto_universe.txt`
- ⚠️ workflow ต้องอยู่บน **default branch** ถึงจะ schedule/dispatch ได้ — ก๊อปไปทั้ง 2 branch
