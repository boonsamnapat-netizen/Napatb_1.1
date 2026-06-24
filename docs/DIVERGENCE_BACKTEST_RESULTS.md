# Divergence Backtest — Best Timeframe (1-year, real data)

หาว่า timeframe ไหนให้ผลดีที่สุดกับกลยุทธ์ divergence บน **ข้อมูลจริง 1 ปี**
รันบน GitHub Actions (ดึง 1h ผ่าน yfinance → resample → walk-forward backtest)

## Setup
- **เหรียญ:** BTC, ETH, SOL, XRP, BNB, ADA (6 majors)
- **ข้อมูล:** 1h จริง (yfinance) ช่วง ~1 ปีล่าสุด (slice 365 วัน) — base 1h มี ~17,470 แท่ง/เหรียญ
- **กลยุทธ์:** regular divergence (RSI/MACD, auto) → entry แท่งถัดไป (open),
  SL ที่ swing ± 0.5·ATR (floor 0.3%), **TP = 2R**, time-stop 30 แท่ง
- **ต้นทุน:** fee 0.05%/ข้าง (taker) หักเป็นหน่วย R, no look-ahead (pivot ยืนยันด้วย fractal window)
- ผลรวม pool ทุกเหรียญต่อ TF

## ผลรวม (รวมทุกเหรียญ)
| TF | trades | win% | avg R/ไม้ | total R | profit factor | max DD (R) |
|----|-------:|-----:|----------:|--------:|--------------:|-----------:|
| **1d** | 35 | 51% | **+0.240** | +8.38 | **1.61** | **4.03** |
| 2h | 432 | 44% | +0.024 | +10.33 | 1.05 | 17.96 |
| 12h | 55 | 44% | +0.019 | +1.04 | 1.04 | 4.97 |
| 1h | 909 | 44% | +0.005 | +4.55 | 1.01 | 35.09 |
| 6h | 121 | 40% | −0.148 | −17.95 | 0.74 | 26.01 |
| 4h | 188 | 35% | −0.187 | −35.21 | 0.68 | 38.12 |

## สรุป: **TF ที่ดีสุด = 1d (รายวัน)**
- **คุณภาพต่อไม้สูงสุด** (+0.24R) และ **คุ้มความเสี่ยงสุด**: profit factor 1.61, max drawdown แค่ 4R
- **กระจายตัวดี** ไม่ใช่ฟลุคเหรียญเดียว — กำไร 5/6 เหรียญ (BTC 71% WR/+2.29R; ลบเฉพาะ ADA)
- TF เล็ก (4h/6h) ติดลบ: ค่าธรรมเนียม + noise กิน edge — ตรงกับที่ระบบเคย validate
  ("1d มี edge หลังหักค่าธรรมเนียมแข็งสุด ~+0.20R/ไม้, TF เล็กโดน fee กิน")
- **2h** total R สูงสุด (+10.33) แต่มาจาก 432 ไม้ที่ avg แค่ +0.024R และ DD 18R — บางและเสี่ยงกว่ามาก

### ข้อควรระวัง
- ตัวอย่าง 1d น้อย (35 ไม้รวม, 4-7 ไม้/เหรียญ) → ความเชื่อมั่นปานกลาง ควรเก็บผลต่อเนื่อง
- ตัวเลขขึ้นกับพารามิเตอร์ (TP=2R, ATR buffer, fee) — ปรับ `--target-r`, `--fee-pct` แล้วผลเปลี่ยนได้
- เพื่อการศึกษา/ช่วยตัดสินใจ ไม่รับประกันกำไร

## รันซ้ำเอง
```bash
# บนเครื่อง (มีข้อมูลใน data/real/crypto_1h แล้ว)
python signal_divergence_backtest.py --csv-dir data/real/crypto_1h \
  --tfs 1h,2h,4h,6h,12h,1d --days 365 --target-r 2.0

# บน GitHub Actions (ดึงข้อมูลสดเอง + ส่งผลเข้า Telegram)
#   Actions -> "Divergence TF Backtest" -> Run workflow (notify=true)
```
> รันเมื่อ 2026-06-24 บน Actions (workflow `divergence_backtest.yml`)
