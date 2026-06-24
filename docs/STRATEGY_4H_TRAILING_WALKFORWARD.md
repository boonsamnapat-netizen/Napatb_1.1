# 4H — Trailing stop, Walk-forward, และ 1D (ข้อ 2/3/4)

ต่อยอดจาก `STRATEGY_COMPARISON_4H.md` ข้อมูลจริง 6 majors, 1h→resample, fee 0.05%/ข้าง

> ⚠️ เพื่อการศึกษา ไม่รับประกันกำไร

---

## ข้อ 2 — ATR trailing stop (4H, 2 ปี)
เปลี่ยนจาก TP คงที่ → trailing stop (stop ไล่ตาม high − k·ATR, ปล่อยกำไรวิ่ง, max-hold 120):

| กลยุทธ์ | fixed 2R | trail 2× | **trail 3×** | trail 4× |
|---|--:|--:|--:|--:|
| ema_cross | +0.068 | +0.374 | **+0.481** (PF 1.89) | +0.427 |
| **bos_retest** | +0.087 | +0.145 | **+0.339** (PF 1.55) | +0.189 |
| donchian | −0.019 | +0.205 | +0.181 | +0.250 |
| liq_sweep | −0.039 | +0.070 | +0.281 | +0.094 |
| supertrend | +0.016 | +0.064 | +0.114 | +0.018 |
| divergence | −0.092 | −0.137 | −0.079 | −0.137 |

→ **trailing ดันสายเทรนด์ขึ้นชัด** (divergence ยังลบ เพราะเป็น reversal) ดูเหมือน ema_cross ดีสุด...
แต่ **per-coin บอกว่าเปราะ**: ema_cross+3× มาจาก ADA +1.50R / XRP +0.91R / SOL +0.65R
แต่ **BNB −0.30R (PF 0.51), BTC +0.05R** → กระจุก 3 alt

## ข้อ 3 — Walk-forward (ตัวตัดสิน over-fit) ⭐
แบ่งเวลา in-sample 65% (เก่า) / out-of-sample 35% (ใหม่), จูนบน IS แล้ววัดบน OOS:

| กลยุทธ์ (trail 3×) | IS avgR | **OOS avgR** | OOS PF | สรุป |
|---|--:|--:|--:|---|
| **bos_retest** | +0.75 | **+0.37** | **1.61** | ✅ edge จริง |
| ema_cross | +0.85 | **−0.24** | 0.62 | ❌ over-fit |

- **bos_retest ทน OOS** และ **ไม่ไวต่อพารามิเตอร์** (จูน vs default OOS ใกล้กัน: +0.37 vs +0.33)
- **ema_cross พังนอกตัวอย่าง** — ตัวเลข IS ที่สวย (+0.85R) เป็นภาพลวงจาก alt bull run ที่ไม่เกิดซ้ำ
- บทเรียน: **avg R สูงใน-sample ไม่พอ ต้องดู OOS** — walk-forward แยกของจริงออกจากของหลอกได้

## ข้อ 4 — bos_retest บน 1D
| กลยุทธ์ (1D, fixed 2R, 2 ปี) | ไม้ | avg R | PF |
|---|--:|--:|--:|
| ema_cross | 33 | +0.428 | 1.83 |
| supertrend | 51 | +0.144 | 1.25 |
| divergence | 55 | +0.023 | 1.05 |
| bos_retest | 68 | +0.001 | 1.00 |

→ บน 1D **bos_retest แทบเสมอตัว** (ไม่เด่นเหมือน 4H) ส่วน 1D+trailing ตัวอย่างน้อยมาก
(17–45 ไม้) เชื่อถือไม่ได้ — **bos_retest เป็นของ 4H, ไม่ใช่ 1D**
(divergence ยังเป็นตัวเลือกฝั่ง 1D ดูผล 1 ปีใน `DIVERGENCE_BACKTEST_RESULTS.md`)

---

## สรุปรวม (สำคัญสุด)
**ระบบที่ robust ที่สุดที่ทดสอบมาทั้งหมด = `bos_retest` บน 4H + ATR trailing 3×**
- OOS-validated (+0.37R/ไม้, PF 1.61) — ไม่ใช่ over-fit
- broad-based (fixed 2R บวก 5/6 เหรียญ รวม BTC)
- ไม่ไวต่อพารามิเตอร์ (window/retest_bars)
- ⚠️ win rate ~30–34% (ชนะน้อย กำไรก้อนโต) — ต้องมีวินัยถือไม้แพ้ติดกัน

**อย่าหลงกับ ema_cross** — IS สวยแต่ OOS ขาดทุน (กระจุก alt, regime-dependent)

## execution note
ผล backtest ที่ดีสุดใช้ **trailing stop** ไม่ใช่ TP คงที่ ดังนั้นเวลาเทรดจริงจาก
สัญญาณ `signal_strategy_live.py` ควรใช้ trailing (≈3×ATR) แทนการปิดที่ TP1/2/3 ตายตัว
(เลข TP ในข้อความเป็นแนวอ้างอิงระยะ R)

## รันซ้ำเอง
```bash
# trailing
python signal_strategy_compare.py --csv-dir data/real/crypto_1h --tf 4h \
  --days 730 --trail-atr 3.0 --max-hold 120 --per-coin
# walk-forward
python signal_walkforward.py --csv-dir data/real/crypto_1h --tf 4h --strategy bos_retest
```
