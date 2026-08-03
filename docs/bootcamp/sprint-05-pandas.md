# Sprint 5 — Data Transformation ด้วย pandas

**สัปดาห์ 15–18 · ~20 ชม. · เครื่องมือ: pandas, numpy**

---

## เป้าหมาย

pandas คือเครื่องมือที่คุณจะใช้มากที่สุดในอาชีพนี้ — งาน data analyst จริง ๆ
คือการนั่งแปลงข้อมูลด้วย pandas 60–70% ของเวลา

ข่าวดี: ทุกอย่างใน pandas คือสิ่งที่คุณเรียนมาแล้วใน Sprint 1–2 แค่เขียนต่างกัน

| Sheets (S1) | SQL (S2) | pandas (S5) |
|---|---|---|
| `FILTER` | `WHERE` | `df[df.close > 50000]` |
| Pivot table | `GROUP BY` | `df.groupby('symbol').mean()` |
| `VLOOKUP` | `JOIN` | `df.merge(other, on='date')` |
| `SORT` | `ORDER BY` | `df.sort_values('close')` |
| — | `LAG()` | `df.close.shift(1)` |
| — | window function | `df.close.rolling(20).mean()` |

---

## สัปดาห์ 15 — พื้นฐาน pandas

### เรียน (2 ชม.)

**Series กับ DataFrame**
- `Series` = คอลัมน์เดียว มี index
- `DataFrame` = ตาราง = หลาย Series ที่ใช้ index ร่วมกัน

**index คือหัวใจที่คนมองข้าม** — pandas จัดแถวให้ตรงกันอัตโนมัติด้วย index
เมื่อคุณบวกสอง Series เข้าด้วยกัน มันจะจับคู่ตาม index ไม่ใช่ตามตำแหน่ง
นี่คือทั้งพลังและกับดักของ pandas

```python
import pandas as pd

df = pd.read_csv("data/real/crypto/BTCUSDT.csv",
                 parse_dates=["Date"], index_col="Date")

df.head()          # 5 แถวแรก
df.info()          # ชนิดข้อมูล + จำนวนค่าที่ไม่ว่าง — ดูทุกครั้งที่โหลดไฟล์ใหม่
df.describe()      # สถิติสรุป
df.shape           # (3135, 5)
df.index.min(), df.index.max()
```

**เลือกข้อมูล — `.loc` กับ `.iloc`**
```python
df["Close"]                          # หนึ่งคอลัมน์ → Series
df[["Open", "Close"]]                # หลายคอลัมน์ → DataFrame
df.loc["2024-01-01"]                 # เลือกด้วย label (ชื่อ index)
df.loc["2024-01-01":"2024-12-31"]    # ช่วง — loc รวมปลายทางด้วย
df.iloc[0]                           # เลือกด้วยตำแหน่ง (แถวแรก)
df.iloc[-20:]                        # 20 แถวสุดท้าย — iloc ไม่รวมปลายทาง
df.loc[df.Close > 60000, ["Close", "Volume"]]
```

⚠️ `.loc` รวมปลายช่วง แต่ `.iloc` ไม่รวม — ต่างจาก slicing ปกติของ Python
เรื่องนี้ทำให้ off-by-one error บ่อยมาก จำให้ขึ้นใจ

**กรอง**
```python
df[df.Close > 60000]
df[(df.Close > 60000) & (df.Volume > df.Volume.mean())]   # ต้องมีวงเล็บ!
df[df.index.year == 2024]
df.query("Close > 60000 and Volume > 1e9")                # อ่านง่ายกว่าเมื่อเงื่อนไขเยอะ
```
⚠️ ใช้ `&` `|` `~` ไม่ใช่ `and` `or` `not` และต้องใส่วงเล็บครอบทุกเงื่อนไข
เพราะลำดับความสำคัญของ `&` สูงกว่า `>` — ลืมวงเล็บแล้วจะได้ error งง ๆ

**สร้างคอลัมน์ใหม่**
```python
df["change"]     = df.Close.pct_change()
df["range_pct"]  = (df.High - df.Low) / df.Open
df["ma20"]       = df.Close.rolling(20).mean()
df["above_ma"]   = df.Close > df.ma20
df["direction"]  = np.where(df.Close > df.Open, "up", "down")
```

### ฝึก (3 ชม.)
1. โหลด BTCUSDT.csv คำนวณผลตอบแทนรายวัน, MA20, MA50, range%
2. หา 20 วันที่ผันผวนสุด แสดงเฉพาะคอลัมน์ที่เกี่ยวข้อง
3. เทียบผลตอบแทนเฉลี่ยของแต่ละปี — ปีไหนดีสุด แย่สุด
4. เขียนซ้ำข้อ 2 จาก Sprint 3 (ที่เขียนด้วย Python เปล่า) ด้วย pandas
   แล้วเทียบจำนวนบรรทัด — นี่คือเหตุผลที่มี pandas

---

## สัปดาห์ 16 — Missing data, groupby, merge

### เรียน (2 ชม.)

**ข้อมูลหาย — เรื่องที่ต้องคิด ไม่ใช่แค่กด fillna**
```python
df.isna().sum()              # นับค่าว่างต่อคอลัมน์ — ทำก่อนเสมอ
df.dropna()                  # ตัดแถวที่มีค่าว่าง
df.fillna(0)                 # ❌ อันตรายมากกับข้อมูลราคา — ราคา 0 ไม่มีจริง
df.ffill()                   # เติมด้วยค่าก่อนหน้า — สมเหตุสมผลกับราคา
df.interpolate()             # เติมด้วยเส้นตรงระหว่างจุด
```

**กฎ:** ก่อนเติมค่าว่าง ต้องตอบให้ได้ว่า**ทำไมมันหาย**
- ตลาดปิด (หุ้นเสาร์อาทิตย์) → ไม่ต้องเติม มันไม่มีจริง
- เหรียญยังไม่ลิสต์ → ไม่ต้องเติม ตัดช่วงนั้นทิ้ง
- API พลาด → เติมด้วย `ffill` ได้
- ⚠️ **ห้าม** เติมด้วยค่าเฉลี่ยทั้งคอลัมน์ในข้อมูล time series
  เพราะค่าเฉลี่ยคำนวณจากอนาคตด้วย = leakage (Sprint 9)

**groupby — สามขั้น split-apply-combine**
```python
df.groupby(df.index.year)["change"].mean()
df.groupby([df.index.year, df.index.month])["change"].agg(["mean","std","count"])

df.groupby(df.index.year).agg(
    avg_return = ("change", "mean"),
    volatility = ("change", "std"),
    best_day   = ("change", "max"),
    n_days     = ("change", "count"),
)
```

**transform vs agg** — ความต่างที่สำคัญ
```python
df.groupby("symbol")["change"].mean()        # agg  → ยุบเหลือ 1 แถวต่อกลุ่ม
df.groupby("symbol")["change"].transform("mean")  # transform → คืนขนาดเท่าเดิม
```
`transform` คือ window function ของ SQL — ใช้ตอนอยากเทียบค่าแต่ละแถวกับค่าเฉลี่ยกลุ่มตัวเอง

**merge / concat**
```python
merged = btc.merge(eth, on="Date", suffixes=("_btc","_eth"), how="inner")
all_coins = pd.concat([btc, eth, sol], keys=["BTC","ETH","SOL"], names=["symbol"])
```

**Long vs Wide — แนวคิดที่ต้องเข้าใจ**
```python
# wide: หนึ่งคอลัมน์ต่อเหรียญ — เหมาะกับการคำนวณ correlation
wide = long_df.pivot(index="Date", columns="symbol", values="Close")

# long: หนึ่งแถวต่อ (วัน, เหรียญ) — เหมาะกับ groupby และการวาดกราฟ
long = wide.reset_index().melt(id_vars="Date", var_name="symbol", value_name="close")
```

### ฝึก (3 ชม.)
1. โหลดทั้ง 20 เหรียญเป็น DataFrame เดียวแบบ long (มีคอลัมน์ `symbol`)
2. ใช้ `groupby` หาสถิติผลตอบแทนของแต่ละเหรียญ: mean, std, max drawdown, จำนวนวัน
3. แปลงเป็น wide แล้วคำนวณ correlation matrix ของผลตอบแทน — เหรียญคู่ไหนไปด้วยกันสุด
4. หาว่าแต่ละเหรียญขาดข้อมูลกี่วัน (เทียบกับปฏิทินเต็ม) แล้วตัดสินใจว่าจะทำยังไง
   — เขียนเหตุผลกำกับ ไม่ใช่แค่เขียนโค้ด

---

## สัปดาห์ 17 — Time series และตัวชี้วัดทางเทคนิค

### เรียน (2 ชม.)

**DatetimeIndex ปลดล็อกความสามารถพิเศษ**
```python
df.loc["2024"]                    # ทั้งปี 2024
df.loc["2024-06"]                 # ทั้งเดือน
df.index.dayofweek                # 0=จันทร์
df.index.quarter

df.resample("W").agg({            # รวมเป็นรายสัปดาห์ — ทำ HTF ในระบบสัญญาณ
    "Open":"first", "High":"max", "Low":"min",
    "Close":"last", "Volume":"sum"
})
df.resample("ME").last()          # รายเดือน
```

**shift / rolling / expanding — สามอย่างที่ใช้ตลอดชีวิต**
```python
df.Close.shift(1)                 # ค่าเมื่อวาน = LAG()
df.Close.shift(-1)                # ค่าพรุ่งนี้ = LEAD() ⚠️ อ่านคำเตือนข้างล่าง
df.Close.rolling(20).mean()       # ค่าเฉลี่ยเคลื่อนที่
df.Close.rolling(20).std()        # ความผันผวนเคลื่อนที่
df.Close.expanding().max()        # ค่าสูงสุดตั้งแต่เริ่มถึงปัจจุบัน — ใช้ทำ drawdown
df.Close.ewm(span=20).mean()      # ค่าเฉลี่ยถ่วงน้ำหนักแบบ exponential
```

> 🚨 `shift(-1)` ดึงอนาคตมา ใช้สร้าง **target** เท่านั้น ห้ามใช้เป็น **feature**
> ทดสอบตัวเองง่าย ๆ: ถ้าวันนี้คือวันที่ 1 มิ.ย. ค่าในคอลัมน์นี้เป็นค่าที่คุณ*รู้ได้จริง*
> ตอนสิ้นวันที่ 1 มิ.ย. ไหม? ถ้าไม่ → มันคือ leakage

**คำนวณตัวชี้วัด**
```python
# Max drawdown
running_max = df.Close.expanding().max()
drawdown    = (df.Close - running_max) / running_max
max_dd      = drawdown.min()

# ATR (Average True Range) — วัดความผันผวนจริง
prev_close = df.Close.shift(1)
tr = pd.concat([
    df.High - df.Low,
    (df.High - prev_close).abs(),
    (df.Low  - prev_close).abs(),
], axis=1).max(axis=1)
df["atr14"] = tr.rolling(14).mean()

# RSI
delta = df.Close.diff()
gain  = delta.clip(lower=0).rolling(14).mean()
loss  = (-delta).clip(lower=0).rolling(14).mean()
df["rsi"] = 100 - 100 / (1 + gain / loss)
```

**Performance — เมื่อไหร่ต้องแคร์**
```python
df.apply(lambda r: ..., axis=1)      # ช้ามาก หลีกเลี่ยง
df.Close * 2                         # เร็ว — vectorized
np.where(cond, a, b)                 # เร็ว
```
กฎ: ถ้าเขียน `for` วนแถวใน pandas แปลว่ามีวิธีที่ดีกว่าเกือบเสมอ

### ฝึก (3 ชม.)
1. เขียนฟังก์ชันคำนวณ ATR, RSI, MACD จากศูนย์
2. เทียบผลลัพธ์กับ `src/signal/indicators.py` ใน repo นี้ — ตรงกันไหม ต่างตรงไหน เพราะอะไร
3. Resample ข้อมูลรายวันเป็นรายสัปดาห์ แล้วตรวจว่าราคาปิดสัปดาห์ตรงกับวันศุกร์/อาทิตย์จริง
4. สร้างคอลัมน์ `target` = ราคาพรุ่งนี้สูงกว่าวันนี้ไหม แล้วเขียนคอมเมนต์กำกับว่า
   ทำไมคอลัมน์นี้ห้ามอยู่ในชุด feature

---

## สัปดาห์ 18 — โปรเจกต์ส่ง

### โปรเจกต์ — Market Behavior Report (5 ชม.)

สร้าง `bootcamp/sprint05/analysis.ipynb` + `report.md`

**ส่วนที่ 1: Data quality report**
วิเคราะห์ทั้ง 20 เหรียญ รายงาน:
- ช่วงวันที่ของแต่ละเหรียญ, จำนวนแถว, วันที่หาย
- แถวผิดปกติ: `High < Low`, `Volume = 0`, ราคากระโดดเกิน 50% ในวันเดียว
- ตัดสินใจว่าจะทำยังไงกับแต่ละปัญหา **พร้อมเหตุผล**

**ส่วนที่ 2: สถิติเชิงพรรณนา**
ตารางเดียวที่มีทุกเหรียญ พร้อมคอลัมน์:
ผลตอบแทนสะสม, ผลตอบแทนเฉลี่ยรายวัน, ความผันผวนรายปี,
Sharpe ratio อย่างง่าย, max drawdown, % วันเขียว, ผลตอบแทนวันที่ดี/แย่ที่สุด

**ส่วนที่ 3: ความสัมพันธ์**
- Correlation matrix ของผลตอบแทนรายวันทั้ง 20 เหรียญ
- Rolling correlation 90 วันระหว่าง BTC กับ altcoin แต่ละตัว — มันคงที่ไหม
- ⚠️ คำถามสำคัญ: correlation ในช่วงตลาดตก ต่างจากช่วงปกติไหม
  (คำนวณแยกสองช่วงแล้วเทียบ) คำตอบมีผลโดยตรงกับการกระจายความเสี่ยง

**ส่วนที่ 4: Regime analysis**
แบ่งช่วงเวลาเป็น bull / bear / sideways ด้วยกฎที่คุณนิยามเอง (เช่น เทียบ MA200)
แล้วเทียบว่าสถิติในส่วนที่ 2 ต่างกันแค่ไหนในแต่ละ regime

**ส่วนที่ 5: `report.md`**
เขียนภาษาคน 1 หน้า:
- 5 ข้อค้นพบ พร้อมตัวเลข
- 3 ข้อจำกัดของการวิเคราะห์นี้
- 2 คำถามที่ต้องใช้ข้อมูลเพิ่มถึงจะตอบได้

**ข้อกำหนด**
- ไม่มี `for` ที่วนทีละแถวเลย — ใช้ vectorized ทั้งหมด
- notebook รันตั้งแต่ต้นจนจบใหม่ได้โดยไม่ error (`Restart & Run All`)
- ทุก markdown cell อธิบายว่า cell ถัดไปทำอะไรและทำไม

**เกณฑ์ผ่าน:** ทำครบ 5 ส่วน, ส่วนที่ 1 เจอปัญหาจริงในข้อมูล,
`report.md` มีข้อจำกัดที่เป็นรูปธรรม ไม่ใช่ประโยคกว้าง ๆ

---

## Checkpoint

1. `.loc` กับ `.iloc` ต่างกันยังไง โดยเฉพาะเรื่องการรวมปลายช่วง
2. ทำไม `df[df.a > 1 & df.b > 2]` ถึงพัง แต่ `df[(df.a > 1) & (df.b > 2)]` ไม่พัง
3. `groupby().agg()` กับ `groupby().transform()` ต่างกันยังไง
4. ทำไมห้ามเติมค่าว่างในข้อมูลราคาด้วยค่าเฉลี่ยของทั้งคอลัมน์
5. `shift(1)` กับ `shift(-1)` — อันไหนใช้เป็น feature ได้ อันไหนไม่ได้ เพราะอะไร

---

**ต่อไป:** [Sprint 6 — Data Visualization](sprint-06-visualization.md)
