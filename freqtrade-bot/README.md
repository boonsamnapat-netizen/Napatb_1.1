# 🤖 Freqtrade Bot — ชุดเริ่มต้นสำหรับเทรด Crypto ด้วยตัวเอง

โฟลเดอร์นี้คือชุด setup ของ [Freqtrade](https://github.com/freqtrade/freqtrade)
(open-source crypto trading bot ที่ดังที่สุดบน GitHub) พร้อมกลยุทธ์ตัวอย่างและคู่มือภาษาไทย
สำหรับเอาไป **develop ต่อและเทรดเอง**

> ⚠️ **คำเตือนสำคัญ**
> - นี่เป็นเครื่องมือเพื่อ "เรียนรู้และทดสอบ" เทรดคริปโตมีความเสี่ยงสูง อาจขาดทุนทั้งหมดได้
> - **ต้อง backtest + รัน dry-run (เงินปลอม) ให้มั่นใจก่อนเสมอ** ก่อนใช้เงินจริง
> - กลยุทธ์ตัวอย่างในนี้ **ไม่ได้การันตีกำไร** — เป็นแค่โครงให้คุณต่อยอด
> - bot ต้องรัน 24 ชม. ควรรันบนเครื่องตัวเองหรือ VPS (ไม่ใช่ environment ชั่วคราว)

---

## 📁 โครงสร้างไฟล์

```
freqtrade-bot/
├── README.md                       <- ไฟล์นี้
├── gen_sample_data.py              <- สร้างข้อมูลจำลอง (ใช้เฉพาะตอนต่อ exchange ไม่ได้)
├── run_offline_backtest.py         <- รัน backtest แบบ offline (ใช้เฉพาะตอนต่อ exchange ไม่ได้)
└── user_data/
    ├── config.json                 <- ไฟล์ตั้งค่าหลัก (เหรียญ, เงินเดิมพัน, exchange ฯลฯ)
    └── strategies/
        └── SampleEmaRsiStrategy.py <- กลยุทธ์ตัวอย่าง (EMA cross + RSI) คอมเมนต์ไทยครบ
```

---

## 🚀 วิธีติดตั้งบนเครื่องของคุณ

### ตัวเลือกที่ 1: Docker (แนะนำ — ง่ายที่สุด ไม่ต้องลง dependency เอง)

```bash
# 1) ติดตั้ง Docker Desktop ก่อน (docker.com)
# 2) เข้ามาในโฟลเดอร์นี้
cd freqtrade-bot

# 3) ดึง image ของ freqtrade
docker pull freqtradeorg/freqtrade:stable

# ตั้ง alias ให้พิมพ์สั้นลง (จะ map user_data เข้าไปใน container)
# Linux/Mac:
alias ft='docker run --rm -v "$(pwd)/user_data:/freqtrade/user_data" freqtradeorg/freqtrade:stable'
```

### ตัวเลือกที่ 2: ติดตั้งด้วย Python venv

```bash
cd freqtrade-bot
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install freqtrade
```

---

## 📊 ขั้นตอนใช้งาน (ทำตามลำดับ)

### 1️⃣ ดาวน์โหลดข้อมูลราคาย้อนหลัง (ของจริงจาก exchange)

```bash
freqtrade download-data \
  --config user_data/config.json \
  --timerange 20240101-20250601 \
  --timeframe 1h \
  --pairs BTC/USDT ETH/USDT SOL/USDT BNB/USDT
```

### 2️⃣ Backtest — ทดสอบกลยุทธ์กับข้อมูลในอดีต

```bash
freqtrade backtesting \
  --config user_data/config.json \
  --strategy SampleEmaRsiStrategy \
  --timerange 20240101-20250601 \
  --timeframe 1h
```

ดูผลว่า กำไร/ขาดทุนรวม, Win rate, Drawdown, Sharpe เป็นยังไง

### 3️⃣ Hyperopt — ให้ระบบหาค่าพารามิเตอร์ที่ดีที่สุดอัตโนมัติ (ออปชัน)

```bash
freqtrade hyperopt \
  --config user_data/config.json \
  --strategy SampleEmaRsiStrategy \
  --hyperopt-loss SharpeHyperOptLoss \
  --spaces buy sell \
  --epochs 100 \
  --timerange 20240101-20250601
```

(กลยุทธ์ตัวอย่างเปิด `optimize=True` ไว้ที่ `buy_rsi`, `sell_rsi`, `ema_fast`, `ema_slow` แล้ว)

### 4️⃣ Dry-run — เทรดด้วยเงินปลอมแบบ real-time (สำคัญมาก ทำก่อนเงินจริงเสมอ)

`config.json` ตั้ง `"dry_run": true` ไว้แล้ว รันได้เลย:

```bash
freqtrade trade --config user_data/config.json --strategy SampleEmaRsiStrategy
```

### 5️⃣ Live — เทรดเงินจริง (ทำเมื่อมั่นใจผล dry-run แล้วเท่านั้น)

1. สมัคร API key จาก exchange (Binance ฯลฯ) แบบ **เปิดสิทธิ์เทรด แต่ปิดสิทธิ์ถอนเงิน**
2. ใส่ key/secret ใน `config.json` ช่อง `exchange.key` / `exchange.secret`
   (หรือทำเป็นไฟล์ config แยกที่ไม่ commit เข้า git)
3. เปลี่ยน `"dry_run": false`
4. เริ่มด้วยเงินก้อนเล็กก่อน

---

## ⚙️ ปรับแต่งที่ควรรู้ใน `config.json`

| ช่อง | ความหมาย |
|------|----------|
| `max_open_trades` | จำนวนดีลที่เปิดพร้อมกันได้สูงสุด |
| `stake_amount` | เงินต่อ 1 ดีล (USDT) — ใส่ `"unlimited"` เพื่อแบ่งเท่าๆ กัน |
| `dry_run` | `true`=เงินปลอม / `false`=เงินจริง |
| `dry_run_wallet` | เงินตั้งต้นตอน dry-run |
| `timeframe` | กรอบเวลาแท่งเทียน (`5m`/`15m`/`1h`/`4h`/`1d`) |
| `exchange.pair_whitelist` | รายชื่อเหรียญที่จะเทรด |
| `telegram` | เปิดเพื่อสั่งงาน/ดูสถานะผ่าน Telegram |
| `api_server` | เปิดเพื่อใช้หน้าเว็บ FreqUI (เปลี่ยน password/jwt_secret ก่อนใช้จริง!) |

---

## ✏️ แก้กลยุทธ์ของคุณเอง

เปิด `user_data/strategies/SampleEmaRsiStrategy.py` — มี 3 ฟังก์ชันหลัก:
- `populate_indicators()` — คำนวณ indicator (RSI, EMA, MACD, Bollinger ฯลฯ)
- `populate_entry_trend()` — เงื่อนไข "เข้าซื้อ"
- `populate_exit_trend()` — เงื่อนไข "ขายออก"

คัดลอกไฟล์นี้ตั้งชื่อใหม่แล้วแก้ตามไอเดียของคุณ จากนั้น backtest เทียบผลได้เลย
ดูเอกสารเพิ่ม: https://www.freqtrade.io/en/stable/strategy-customization/

---

## 🧪 หมายเหตุ: ไฟล์ทดสอบแบบ offline

`gen_sample_data.py` และ `run_offline_backtest.py` มีไว้เพราะ environment ที่สร้างชุดนี้
**ต่อ exchange API ไม่ได้** (ถูก network policy บล็อก) จึงต้องสร้างข้อมูลจำลองเพื่อพิสูจน์ว่า
ระบบรันได้ครบ end-to-end

**บนเครื่องจริงของคุณไม่ต้องใช้ 2 ไฟล์นี้** — ใช้ `freqtrade download-data` ดึงข้อมูลจริง
แล้ว `freqtrade backtesting` ได้ตามปกติ

---

## 📚 ลิงก์ที่เป็นประโยชน์

- เอกสารหลัก: https://www.freqtrade.io/
- คลัง strategy ตัวอย่างจากชุมชน: https://github.com/freqtrade/freqtrade-strategies
- Discord ชุมชน freqtrade: https://discord.gg/freqtrade
