# Crypto Signal System — คู่มือ

ระบบ generate signal สด ที่บอก **จุดเข้า / จุดออก / Money Management / Risk** โดยใช้
indicator กระแสหลักที่คนในตลาดส่วนใหญ่ใช้ + ข่าวประกอบ

> ⚠️ **คำเตือน:** นี่คือเครื่องมือช่วยตัดสินใจและเพื่อการศึกษา ไม่มีระบบใดรับประกันกำไรได้
> ตลาดมีความไม่แน่นอนและคุณสามารถขาดทุนได้ ใช้ความเสี่ยงที่รับได้และเทรดตามแผนของตัวเองเสมอ

---

## ปรัชญา — "เห็นภาพเดียวกับตลาด แต่ตัดสินใจดีกว่า"

| หลักการ | ทำไม |
|---|---|
| ใช้ indicator ที่คนหมู่มากดู (EMA, RSI, MACD, BB, Stoch, ADX, Volume) | ระดับที่คนส่วนใหญ่เฝ้าดู = liquidity / จุดกลับตัวจริง เราต้องเห็นสิ่งที่ตลาดเห็น |
| **Confluence** — ต้องมีหลายตัวเห็นพ้อง ไม่ใช่ตัวเดียวสั่ง | ลด false signal ตัวเดียวมักหลอก |
| **Multi-timeframe** — เทรดตามเทรนด์ TF ใหญ่เท่านั้น | คนแพ้เพราะสวนเทรนด์ใหญ่ เรากรองออก |
| **ไม่ไล่ราคา** — overbought/oversold สุดขั้ว → รอ ไม่เข้า | ความผิดพลาดคลาสสิกของรายย่อยคือไล่ของแพง |
| **วินัย MM/Risk** — fixed-fractional, ATR stop, R-multiple TP | ตัวที่ทำให้รอดระยะยาวจริง ไม่ใช่ความมั่นใจ |
| **ข่าวเป็น risk gate** ไม่ใช่ตัวสั่งเทรด | เลี่ยงโดน liquidate ตอน event ใหญ่ / fade sentiment สุดขั้ว |

---

## วิธีใช้

```bash
pip install -r requirements.txt

# สัญญาณสด (ดึงข้อมูลจริงผ่าน ccxt/binance)
python signal_cli.py BTCUSDT

# กำหนด timeframe + พอร์ต + ความเสี่ยงต่อไม้
python signal_cli.py ETHUSDT --tf 1h --htf 4h --account 5000 --risk 1.5

# ใส่ข่าวเอง (ทำงาน offline ได้ ไม่ต้องต่อเน็ตข่าว)
python signal_cli.py SOLUSDT --headlines "SEC approves SOL ETF" "Solana TVL ATH"

# โหมด demo (ข้อมูลสังเคราะห์ ทดสอบ offline)
python signal_cli.py BTCUSDT --demo

# เอา JSON ดิบ
python signal_cli.py BTCUSDT --json
```

ตั้งค่า `ANTHROPIC_API_KEY` เพื่อเปิดการวิเคราะห์ข่าวด้วย Claude (ถ้าไม่ตั้ง จะใช้ keyword fallback)

---

## ระบบตัดสินใจอย่างไร (Pipeline)

1. **ดึง OHLCV** 2 timeframe (เทรด + กรองเทรนด์) ผ่าน `ccxt`
2. **คำนวณ indicator** ทั้งหมด (`src/signal/indicators.py`)
3. **ให้คะแนน 4 กลุ่ม** แต่ละกลุ่ม -1..+1 (`score_timeframe`)
   - `trend` — การเรียงตัว EMA + ตำแหน่งราคา ปรับด้วย ADX (เทรนด์อ่อนถูกหรี่)
   - `momentum` — RSI + MACD histogram + Stochastic (หรี่ที่ overbought/oversold)
   - `volatility` — Bollinger %B (เอียงแบบ contrarian: ใกล้ band ล่าง = เด้งขึ้น)
   - `volume` — relative volume + ทิศ OBV (ยืนยันโมเมนตัม)
4. **Composite** = ผลรวมถ่วงน้ำหนัก → ทิศทาง LONG/SHORT/NEUTRAL
5. **Multi-timeframe gate** — ถ้า TF ใหญ่สวนทาง → ลด confidence / อาจ AVOID
6. **Key levels** (`src/signal/levels.py`) — swing high/low + เลขกลม → จุดวาง stop/target
7. **News overlay** (`src/signal/news.py`) — ปรับ `risk_multiplier` และเตือน event ใหญ่
8. **Money management** (`src/signal/money_management.py`)
   - `position size = (พอร์ต × risk%) / ระยะ stop`
   - stop จาก ATR + โครงสร้างราคา (วางเลย level ที่คนหมู่มากวาง เพื่อเลี่ยง stop-hunt)
   - TP หลายชั้นที่ระดับ resistance/support จริง คิดเป็น R-multiple
   - คำนวณ leverage แนะนำ, blended R:R, Expected Value (R)

ผลลัพธ์: `decision` = **ENTER** (เข้าได้) / **WAIT** (รอ setup ดีกว่า) / **AVOID** (เลี่ยง)

---

## ตั้งค่า (`config/config.yaml` → `signal:`)

ปรับน้ำหนัก indicator, periods, threshold, ขนาดพอร์ต, % ความเสี่ยง, feed ข่าว ได้ทั้งหมด
ค่า default เน้น **อนุรักษ์นิยม** — ปฏิเสธ setup คุณภาพต่ำมากกว่าจะเข้าถี่

| คีย์ | ความหมาย |
|---|---|
| `entry_threshold` | \|composite\| ขั้นต่ำที่จะมีทิศทาง |
| `min_confidence` | ต่ำกว่านี้ = WAIT (ไม่เข้า) |
| `atr_stop_mult` / `min_stop_atr` / `max_stop_atr` | กรอบระยะ stop ตาม ATR |
| `risk_per_trade_pct` | % พอร์ตที่เสี่ยงต่อไม้ (แนะนำ 0.5–2%) |
| `weights` | น้ำหนักของ trend/momentum/volatility/volume |

---

## โครงสร้างโค้ด

```
src/signal/
  indicators.py        # EMA, RSI, MACD, BB, ATR, Stoch, ADX, OBV, rVol
  market_data.py       # ดึง OHLCV ผ่าน ccxt + demo generator
  levels.py            # swing points, round numbers, liquidity zones
  money_management.py   # position sizing, R-multiple, EV
  news.py              # RSS/manual headlines + sentiment (Claude หรือ keyword)
  signal_engine.py     # รวมทุกอย่าง → Signal
signal_cli.py          # CLI + การแสดงผล
```

## ทิศทางพัฒนาต่อ
- เชื่อม `src/backtest/` เพื่อ backtest กฎ signal เองและวัด win-rate จริง (แทนค่าสมมติ)
- ปฏิทินข่าวเศรษฐกิจ (เวลา event แน่นอน) แทนการเดาจากพาดหัว
- ส่ง alert เข้า Discord/Telegram เมื่อ decision = ENTER
- ปรับ weights อัตโนมัติจากผล backtest (walk-forward)
