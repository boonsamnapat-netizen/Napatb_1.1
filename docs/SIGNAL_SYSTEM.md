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

---

## Telegram alerts (ยิง signal เข้ามือถือ)

`src/signal/notifier.py` — ส่ง signal ตอน `decision == ENTER` เข้า Telegram พร้อม
entry/SL/TP/size/portfolio ตั้ง env `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`
(จาก @BotFather) ถ้าไม่ตั้ง = dry-run (พิมพ์ข้อความที่จะส่งให้ดู)

```bash
python signal_cli.py BTCUSDT --notify              # alert ตอน ENTER
python signal_scan.py --csv-dir data/real/crypto_1h --htf 4h --portfolio --notify
```

> รันบนเครื่อง/Actions ที่ออกเน็ตได้ (sandbox dev ส่ง api.telegram.org ไม่ได้)

**ความปลอดภัย:** มี floor `min_stop_pct` (0.3% ของราคา) กัน position size/leverage ระเบิด
เมื่อ ATR จิ๋ว + guard ปฏิเสธข้อมูล flat/stale (O=H=L=C, เหรียญ delisted) อัตโนมัติ

---

## Portfolio risk management + ค่าธรรมเนียม (maker/taker)

**Portfolio heat** (`src/signal/portfolio.py`, `signal_scan --portfolio`) — เปิดหลาย
position พร้อมกันในคริปโตไม่ใช่กระจายความเสี่ยงจริง เพราะทุกเหรียญวิ่งตาม BTC
(all-longs = เดิมพัน BTC beta ก้อนเดียว) จึงคุม:
- `max_portfolio_heat_pct` — ความเสี่ยงรวมทุก position (default 6%)
- `max_per_direction_heat_pct` — เพดานต่อทิศ (correlation-aware, default 4%)
- `max_concurrent` — จำนวน position พร้อมกัน (default 5)
- กระจาย budget ความเสี่ยงให้ setup ที่อันดับดีสุดก่อน + คำนวณ size/leverage ให้

**ค่าธรรมเนียม (maker vs taker)** — ทดสอบจริงบน 4h majors net of fees:

| วิธี | exp(R) | เทียบ |
|---|---|---|
| Taker ทั้งหมด (0.05%+slip) | +0.108R | baseline |
| Maker entry (limit) | +0.129R | +19% |
| Maker entry + TP exits | +0.137R | **+27%** |

backtester คิดต้นทุนตาม path จริง: limit (maker 0.02%) สำหรับ entry/TP, market (taker)
สำหรับ stop เสมอ → `signal.backtest.maker_entries` / `maker_exits` (default: exits=on)

---

## สิ่งที่ยืมจาก open-source bots (Freqtrade/Jesse) + ผลที่วัดได้

เรียนจากโปรเจกต์ที่คนลองผิดลองถูกมาเยอะ แล้ว A/B บนข้อมูลจริง (4h, 18 เหรียญ, net of fees):

| เทคนิค (ที่มา) | ผล A/B | ใช้ไหม |
|---|---|---|
| ย้าย 1h → 4h/1d (intermediate TF, arxiv/Freqtrade) | net −0.06R → **+0.10R** | ✅ default |
| **Supertrend** confirmation (Freqtrade/Jesse) | ยืนยันเทรนด์, ~เป็นกลางถึงบวกนิด | ✅ ใน trend score |
| **ATR/R trailing stop** ปล่อยกำไรวิ่ง | 2.5R ดีสุด (1.5R แย่ — ตัดเร็วไป) | ✅ `trailing_r: 2.5` |
| **Cooldown** หลังขาดทุน (Freqtrade protection) | กลับแย่ลงเล็กน้อยที่ TF นี้ | ⛔ ปิด (`0`) |
| **Liquidity/pairlist filter** (stick to majors) | alts +0.058R vs majors **+0.108R** | ✅ `scanner.quality_top_n` |

**สรุป config ที่ดีสุดตอนนี้** (net of fees, ~validated): 4h/1d + supertrend + trail 2.5R +
กรองเฉพาะเหรียญ liquid → **~+0.108R/ไม้, WR ~47%, DD ~−9%, บวกทุก major**

> ตั้ง `signal.scanner.quality_top_n: 10` เพื่อให้ scanner เทรดเฉพาะ top-10 ที่ liquidity สูงสุด

---

## ผลทดสอบข้อมูลจริง + บทเรียนเรื่องค่าธรรมเนียม (สำคัญมาก)

ทดสอบบนข้อมูลจริง (ดึงผ่าน GitHub Actions/yfinance) **หักค่าธรรมเนียมแล้ว**
(fee 0.05% + slippage 0.03% ต่อข้าง = round-trip ~0.16% ของ notional):

| Timeframe | เทรด | net exp(R)/ไม้ | สรุป |
|---|---|---|---|
| **1d** | 219 | **+0.198R** | ดีสุด — ทุกเหรียญบวก, DD ต่ำ |
| **4h** | 414 | **+0.096R** | บวกชัด — สมดุลโอกาส/คุณภาพ |
| 1h | 1,923 | **−0.056R** | ขาดทุน — fee กิน edge หมด |

**บทเรียน:** gross 1h ดูดี (+0.063R) แต่เป็นภาพลวงตา — pre-fee. stop แคบบน 1h ทำให้
ต้นทุน `cost_R = 2·(fee+slip)/stop_fraction` พุ่งจนเกิน edge ระบบจึง **default เป็น 4h/1d**
เทรดน้อยลงแต่ R ต่อไม้สูงพอจะชนะค่าธรรมเนียม (= วินัยที่ทำให้ "กำไรมากกว่าตลาด" จริง)

> เปิด/ปรับต้นทุนได้ที่ `signal.backtest.fee_pct` / `slippage_pct`
> ใช้ limit/maker entry (เรามี entry_zone ให้แล้ว) ช่วยลด fee ได้อีกครึ่ง

---

## Scanner — หาเหรียญที่ setup ดีที่สุด ("setup-first")

แทนที่จะถามทีละเหรียญ scanner รัน engine ทั้ง universe แล้ว **จัดอันดับ** ให้เห็นว่า
*ตอนนี้ตัวไหนน่าเข้าที่สุด* — เรียงตามคุณภาพ setup (confluence + R:R + EV) ไม่ใช่ตัวที่ขึ้นแรงสุด

```bash
python signal_scan.py                                  # live: top coins by volume (ccxt)
python signal_scan.py --symbols BTCUSDT ETHUSDT SOLUSDT
python signal_scan.py --csv-dir data/real/crypto --htf W --only-enter --top 15
```

ผลลัพธ์เป็นตารางจัดอันดับ: decision / direction / confidence / entry / stop / R:R / EV
(`src/signal/scanner.py`) — รันแบบขนาน (ThreadPool), news ปิด default เพื่อความเร็ว
แต่ calendar gate ยังทำงาน

---

## ข้อมูลจริง (Real market data)

sandbox dev ต่อ exchange API ไม่ได้ จึงใช้ **GitHub Actions** ดึงข้อมูลจริง (runner มีเน็ต):

- `.github/workflows/fetch_crypto_data.yml` — ดึง crypto OHLCV จริงผ่าน `yfinance`
  (BTC-USD, ETH-USD, …) → commit เป็น CSV ที่ `data/real/crypto/<SYM>.csv`
  - สั่งรันจากแท็บ **Actions → Fetch Real Crypto Data → Run workflow**
  - แก้ universe ได้ที่ `data/crypto_universe.txt`
- บนเครื่องคุณที่ต่อ Binance ได้ → `signal_cli.py` / `signal_scan.py` ดึงสดผ่าน ccxt ตรงๆ

แล้ว backtest/scan กับไฟล์จริง:
```bash
python signal_backtest.py BTCUSDT --csv data/real/crypto/BTCUSDT.csv --htf-rule W --optimize
python signal_scan.py --csv-dir data/real/crypto --htf W
```

CSV loader (`src/signal/market_data.py`) อ่านได้ทั้ง path และ URL (เช่น raw.githubusercontent.com)
รองรับ format มาตรฐาน (Date,Open,High,Low,Close,Volume) และไฟล์ multi-symbol

> หมายเหตุ: ระบบ asset-agnostic — backtest กับหุ้นจริงได้ผลสมจริง เช่น AAPL รายวัน 11 ปี
> ~36 เทรด, WR ~58%, PF ~2.0; MSFT walk-forward OOS WR ~46% แต่ expectancy ยังเป็นบวก
> (กำไรจาก R-multiple ไม่ใช่ win-rate สูง)

---

## Backtest & Walk-forward tuning (วัด win-rate จริง)

`signal_backtest.py` เล่นกฎ signal เดิม **bar-by-bar ไม่มี look-ahead** เพื่อวัด
win-rate / expectancy จริง แล้วป้อนกลับเข้า MM (เลิกใช้ค่าสมมติ)

```bash
# backtest ธรรมดา (in-sample)
python signal_backtest.py BTCUSDT --tf 1h --htf 4h --limit 1500

# walk-forward: จูน weights บนช่วง in-sample แล้ววัดผลเฉพาะ out-of-sample (เลขที่ซื่อสัตย์)
python signal_backtest.py BTCUSDT --optimize --train 500 --test 250

# เขียน calibrated_win_rate กลับเข้า config ให้ MM ใช้ค่าจริง
python signal_backtest.py BTCUSDT --optimize --apply

python signal_backtest.py BTCUSDT --demo      # ทดสอบ offline
```

โมเดลการเทรดตรงกับแผนของ engine: เข้าเมื่อ ENTER, scale out ที่ TP1/TP2/TP3 ตาม
allocation, **เลื่อน stop ไป breakeven หลัง TP1**, ปิดที่เหลือเมื่อโดน stop หรือครบ max hold

> รายงาน metrics: win rate, expectancy (R/ไม้), profit factor, total R,
> max drawdown (R และ %), return แบบทบต้น — เน้นตัวเลข **out-of-sample**
> (in-sample อย่างเดียวมักดูดีเกินจริง)

---

## Economic Calendar (เวลา event จริง)

`config/economic_calendar.yaml` เก็บเวลา event ที่มีผลสูง (FOMC, CPI, NFP, token unlock)
engine บังคับ **blackout window** รอบ event: ลดขนาด/ยืนนอกตลาด (ดู `signal.calendar` ใน config)

- ในช่วง blackout → `risk_multiplier × 0.4` และ downgrade ENTER → WAIT
- มี event ภายใน 12 ชม. → เตือนล่วงหน้า
- กรองตาม asset ได้ (unlock ของ ARB ไม่กระทบ BTC)

อัปเดตไฟล์เองทุกเดือน (ลอกเวลาได้จาก forexfactory / investing.com / token-unlock trackers)
หรือชี้ `signal.calendar.remote_url` ไปยัง JSON feed รูปแบบเดียวกัน

---

## โครงสร้างโค้ด

```
src/signal/
  indicators.py        # EMA, RSI, MACD, BB, ATR, Stoch, ADX, OBV, rVol
  market_data.py       # ดึง OHLCV ผ่าน ccxt + demo generator
  levels.py            # swing points, round numbers, liquidity zones
  money_management.py   # position sizing, R-multiple, EV
  news.py              # RSS/manual headlines + sentiment (Claude หรือ keyword)
  calendar.py          # ปฏิทิน event เวลา จริง + blackout window
  backtester.py        # backtest กฎ signal + walk-forward weight tuning
  scanner.py           # สแกนทั้ง universe + จัดอันดับ setup
  signal_engine.py     # รวมทุกอย่าง → Signal
signal_cli.py          # CLI สร้าง signal สด (ทีละเหรียญ)
signal_scan.py         # CLI สแกนหา setup ดีที่สุดทั้งตลาด
signal_backtest.py     # CLI backtest / จูน weights
config/economic_calendar.yaml      # ตารางข่าว
data/crypto_universe.txt           # รายชื่อเหรียญสำหรับ workflow
.github/workflows/fetch_crypto_data.yml   # ดึง crypto จริงผ่าน Actions
```

## ทิศทางพัฒนาต่อ
- ✅ backtest กฎ signal + วัด win-rate จริง (walk-forward)
- ✅ ปฏิทินข่าวเศรษฐกิจ (เวลา event แน่นอน)
- ✅ scanner หาเหรียญที่ setup ดีที่สุดทั้งตลาด
- ✅ ข้อมูลจริงผ่าน GitHub Actions (yfinance) + CSV/URL loader
- ⏳ ส่ง alert เข้า Telegram เมื่อ decision = ENTER (ขั้นต่อไป — ตอนยิงจริง)
- คิดค่า fee / slippage / funding ในการ backtest ให้สมจริงยิ่งขึ้น
