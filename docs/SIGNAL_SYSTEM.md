# Crypto Signal System — Reference

ระบบ signal crypto: สแกนตลาด → จัดอันดับ setup → คำนวณ MM/Risk → ยิงแจ้งเตือนไทย
(+กราฟ) เข้า Telegram ทำงานเองบน GitHub Actions

> ⚠️ เครื่องมือช่วยตัดสินใจ/เพื่อการศึกษา ไม่รับประกันกำไร ใช้ตัวเลขที่หักค่าธรรมเนียม + out-of-sample เสมอ

---

## ปรัชญา — "เห็นภาพเดียวกับตลาด แต่ตัดสินใจดีกว่า"
ใช้ indicator กระแสหลัก (EMA/RSI/MACD/BB/Stoch/ADX/Volume/Supertrend) → ระดับที่คนหมู่มากดู = liquidity จริง
จุดต่าง: **confluence หลายตัว + เทรดตามเทรนด์ TF ใหญ่ + ไม่ไล่ราคา + วินัย MM/Risk + ข่าว/event เป็น risk gate**

## ผลที่ validate แล้ว (ข้อมูลจริง, net of fees, walk-forward OOS)
| สิ่งที่พบ | ค่า |
|---|---|
| TF ที่ทำกำไร (หลังหัก fee) | **1d +0.20R, 4h +0.10R** — 1h ติดลบ (fee กิน stop แคบ) |
| Majors รวม OOS | **+0.087R/ไม้** (45% WR, กำไรจาก R-multiple) |
| ใช้ maker (limit) entry/TP | ดันเป็น **+0.137R/ไม้** |
| Liquidity filter (majors) | +0.108R vs alts +0.058R |
| Drawdown ต่อเหรียญ | −10..−30% (กระจายพอร์ตช่วยลด) |

**Default = combo ที่ดีสุด:** 4h/1d + Supertrend + ATR trailing 2.5R + cooldown OFF + กรอง majors + BTC regime gate

---

## โครงสร้าง `src/signal/`
```
indicators        EMA/RSI/MACD/BB/ATR/Stoch/ADX/OBV/rVol/Supertrend/regime
levels            swing high/low + round numbers (liquidity zones)
market_data       ccxt + CSV/URL loader + resample + demo generator
signal_engine     สมอง: confluence score → ENTER/WAIT/AVOID + entry/SL/TP
money_management   position sizing (fixed-fractional), R-multiple TP, EV
portfolio         heat cap, per-direction correlation cap, concurrency
scanner           รัน engine ทั้ง universe → จัดอันดับ + liquidity filter
backtester        walk-forward + fee model (maker/taker) + trailing/cooldown
calendar          ปฏิทิน event (FOMC/CPI...) → blackout window
news              RSS/keyword sentiment (Claude ถ้ามี ANTHROPIC_API_KEY)
notifier          Telegram (text/photo) ภาษาไทย + คำแนะนำ + weekly scorecard
charting          กราฟ PNG (candles + EMA + Entry/SL/TP) แนบ alert
analytics         คำนวณผลจาก trade: equity/drawdown/R-dist/Sharpe/Sortino/Kelly + breakdown เหรียญ/ทิศ/confidence/เดือน
dashboard         เรนเดอร์ HTML dashboard (inline SVG ไม่พึ่ง dep ภายนอก) + export PNG
```
CLI: `signal_cli.py` (ทีละเหรียญ) · `signal_scan.py` (สแกน+แจ้งเตือน) · `signal_backtest.py` (backtest/จูน) · `signal_report.py` (dashboard วัดผล)

---

## คำสั่งที่ใช้บ่อย
```bash
# สัญญาณทีละเหรียญ (offline)
python signal_cli.py BTCUSDT --demo

# สแกน + portfolio + สรุป + แจ้งเตือน + กราฟ (โหมด CSV)
python signal_scan.py --csv-dir data/real/crypto --htf W --portfolio --summary --notify --charts

# backtest บนข้อมูลจริง + walk-forward + เขียน calibrated_win_rate กลับ config
python signal_backtest.py BTCUSDT --csv data/real/crypto/BTCUSDT.csv --htf-rule W --optimize --apply

# วัดผลรวมทั้ง universe → HTML dashboard + PNG + JSON (+ ส่ง scorecard ไทยเข้า Telegram)
python signal_report.py --csv-dir data/real/crypto --htf-rule W --notify
```
> sandbox ต่อ exchange ไม่ได้ → ใช้ `--csv*`/`--demo`; บนเครื่องที่ต่อ Binance ได้ใช้ live ccxt

## Config — `config/config.yaml` (`signal:`)
| คีย์ | ค่า/ความหมาย |
|---|---|
| entry_timeframe / htf_timeframe | `4h` / `1d` |
| min_confidence | 55 (ต่ำกว่า = WAIT) |
| account_size / risk_per_trade_pct / leverage | 100 / 2% / 10 (leverage = แสดง margin เท่านั้น ความเสี่ยงคุมที่ %) |
| backtest.fee_pct/slippage_pct/maker_fee_pct | 0.05% / 0.03% / 0.02% (maker_exits: on) |
| backtest.trailing_r / cooldown_bars | 2.5 / 0 |
| scanner.quality_top_n / use_regime | กรอง top-N liquid / BTC regime gate |
| min_stop_pct | 0.3% floor (กัน leverage ระเบิดเมื่อ ATR จิ๋ว) |

อัปเดตทุนจริง: ส่ง `/port 150` หาบอท → เขียน `data/account.json` (ดู `docs/TELEGRAM_SETUP.md`)

---

## Deploy (อัตโนมัติบน Actions)
`.github/workflows/auto_scan_alert.yml` — รายวัน 01:00 UTC (08:00 ไทย):
fetch (yfinance) → scan → ยิงสรุปไทย + สัญญาณ compact แยกเหรียญ + กราฟ เข้า Telegram
- Secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- Inputs: `test_notify` (เทสการเชื่อมต่อ), `sample_signal` (ส่งตัวอย่าง)
- workflow ต้องอยู่บน **default branch** ถึงจะ schedule/dispatch ได้ → แก้ทั้ง 2 branch
- ข้อมูล: `data/real/crypto/*.csv` (1d), `data/real/crypto_1h/` (1h); universe = `data/crypto_universe.txt`

## Performance dashboard (`signal_report.py` → `reports/`)
รัน walk-forward ทั้ง universe → เก็บ trade รายไม้ (พร้อมวันที่) → ให้คะแนน forward-test log →
สร้าง `reports/performance.html` (KPI + equity/drawdown/R-dist + ตารางรายเหรียญ/confidence/ทิศ/เดือน) +
`performance.json` + PNG. รันเองทุกสัปดาห์ผ่าน `.github/workflows/weekly_report.yml` (Sun 09:00 ไทย)
- ทุกตัวเลขเป็น walk-forward **OOS หักค่าธรรมเนียม/slippage** แล้ว; Sharpe/Sortino = ต่อไม้ (info ratio) ไม่ใช่รายปี
- Equity/Drawdown/Compounded รวม = ต่อทุกไม้ทุกเหรียญเรียงกัน (มุมมองแย่สุด ไม่นับกระจายพอร์ต) →
  max DD รวมเกินจริง; DD จริงต่อเหรียญดูคอลัมน์ “Max DD” ในตารางรายเหรียญ
- ค่าที่เชื่อได้สุด: **expectancy/ไม้** + **Total R** + **breakdown ตาม confidence** (75+ = edge ชัดสุด)

## งานที่ทำต่อได้
เพิ่มเหรียญ (universe.txt) · เปลี่ยน cron · เพิ่ม RSI/Volume panel ในกราฟ · ปฏิทิน event แบบ feed ·
เชื่อม auto-trade เข้า exchange · จูน weights จาก backtest จริง ·
publish `reports/performance.html` ขึ้น GitHub Pages · เพิ่ม rolling 90-วันใน dashboard
