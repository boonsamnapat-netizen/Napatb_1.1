# Sprint 6 — Data Visualization

**สัปดาห์ 19–21 · ~15 ชม. · เครื่องมือ: matplotlib, seaborn, plotly**

---

## เป้าหมาย

กราฟไม่ได้มีไว้ให้สวย มีไว้ให้**คนตัดสินใจได้เร็วขึ้น**
sprint นี้สอนสองอย่าง: เขียนโค้ดวาดกราฟให้เป็น และเลือกกราฟให้ถูก

อย่างที่สองยากกว่าและสำคัญกว่ามาก

---

## สัปดาห์ 19 — matplotlib และการเลือกกราฟ

### เรียน (2 ชม.)

**เลือกกราฟจากคำถาม ไม่ใช่จากความสวย**

| คำถาม | กราฟที่ใช้ | ห้ามใช้ |
|---|---|---|
| ค่านี้เปลี่ยนตามเวลายังไง | เส้น (line) | pie |
| กลุ่มไหนมากกว่ากัน | แท่ง (bar) | pie เมื่อมีเกิน 3 กลุ่ม |
| ข้อมูลกระจายตัวยังไง | histogram, box, violin | bar ของค่าเฉลี่ย |
| สองตัวแปรสัมพันธ์กันไหม | scatter | เส้นเชื่อมจุด |
| สัดส่วนของทั้งหมด | stacked bar, treemap | pie ที่มี 8 ชิ้น |
| ความสัมพันธ์หลายคู่ | heatmap | ตารางตัวเลขล้วน |

**กฎที่ไม่ควรฝ่าฝืน**
1. **แกน y ของกราฟแท่งต้องเริ่มที่ 0** — ไม่งั้นคือการโกหกด้วยภาพ
   (กราฟเส้นไม่จำเป็น เพราะคนอ่านว่ามันคือแนวโน้ม ไม่ใช่ขนาด)
2. **บอกหน่วยเสมอ** — `$`, `%`, `R` ใส่ในชื่อแกน
3. **ชื่อกราฟต้องบอกข้อสรุป ไม่ใช่บอกว่าวาดอะไร**
   ❌ "ผลตอบแทนรายเดือนของ BTC"
   ✅ "BTC ให้ผลตอบแทนบวกใน 7 จาก 12 เดือน แต่กระจุกที่ไตรมาส 4"
4. **ลบสิ่งที่ไม่ช่วยตัดสินใจออก** — เส้นตาราง 3D, เงา, gradient ไม่จำเป็น

**โครงสร้าง matplotlib**
```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(12, 6))       # ใช้แบบนี้เสมอ ไม่ใช่ plt.plot() ลอย ๆ
ax.plot(df.index, df.Close, linewidth=1.2, label="Close")
ax.plot(df.index, df.ma20,  linewidth=1.0, label="MA20", alpha=0.8)
ax.set_title("BTC ปิดเหนือ MA20 เพียง 51.7% ของวัน ตั้งแต่ 2018")   # ตัวเลขจริงจากข้อมูลใน repo
ax.set_xlabel("วันที่")
ax.set_ylabel("ราคา (USD)")
ax.legend()
ax.grid(alpha=0.25)
fig.tight_layout()
fig.savefig("chart.png", dpi=150)
```

`fig` คือกระดาษ `ax` คือกราฟบนกระดาษ — หนึ่ง fig มีหลาย ax ได้
เข้าใจสองอย่างนี้แล้ว matplotlib จะไม่งงอีกเลย

**หลายกราฟในภาพเดียว**
```python
fig, axes = plt.subplots(2, 2, figsize=(14, 10))
axes[0,0].plot(...)
axes[0,1].hist(...)
```

**ภาษาไทยในกราฟ** — matplotlib ไม่มีฟอนต์ไทยมาให้
```python
import matplotlib.font_manager as fm
plt.rcParams["font.family"] = "Tahoma"    # หรือฟอนต์ไทยที่มีในเครื่อง
plt.rcParams["axes.unicode_minus"] = False
```
ถ้าเห็นสี่เหลี่ยม □□□ แทนตัวหนังสือ = ปัญหาฟอนต์ ไม่ใช่ปัญหาโค้ด
(`src/signal/charting.py` ใน repo นี้เจอปัญหาเดียวกัน ไปดูว่าแก้ยังไง)

### ฝึก (3 ชม.)
1. วาดกราฟราคา BTC + MA20 + MA50 พร้อมชื่อกราฟที่บอกข้อสรุป
2. Histogram ของผลตอบแทนรายวัน — สังเกตหางสองข้าง เทียบกับเส้นโค้งปกติ
3. Scatter ผลตอบแทน BTC vs ETH พร้อมเส้นแนวโน้ม
4. Subplot 2x2 แสดง 4 เหรียญพร้อมกัน ใช้แกน y เดียวกันเพื่อเทียบได้

---

## สัปดาห์ 20 — seaborn, plotly และกราฟการเงิน

### เรียน (2 ชม.)

**seaborn** — เขียนสั้นกว่าสำหรับกราฟสถิติ
```python
import seaborn as sns
sns.heatmap(corr, annot=True, cmap="RdBu_r", center=0, vmin=-1, vmax=1)
sns.boxplot(data=long_df, x="symbol", y="change")
sns.violinplot(data=long_df, x="year", y="change")
sns.pairplot(df[["btc","eth","sol"]])
```

⚠️ heatmap ของ correlation ต้องใช้ **diverging colormap** ที่มีจุดกลางที่ 0
(`RdBu_r`, `coolwarm`) ห้ามใช้ `viridis` หรือ `hot` เพราะ correlation -0.8 กับ +0.8
ต่างกันคนละเรื่อง แต่ colormap แบบไล่สีเดียวจะทำให้ดูใกล้เคียงกัน

**plotly** — กราฟโต้ตอบได้ ซูมได้ hover ดูค่าได้
```python
import plotly.graph_objects as go

fig = go.Figure(data=[go.Candlestick(
    x=df.index, open=df.Open, high=df.High, low=df.Low, close=df.Close)])
fig.update_layout(title="BTC/USDT รายวัน", xaxis_rangeslider_visible=False)
fig.write_html("candlestick.html")
```

**กราฟการเงินที่ควรวาดเป็น**

| กราฟ | บอกอะไร |
|---|---|
| Candlestick | ราคา OHLC ในภาพเดียว |
| Equity curve | เงินในพอร์ตเดินยังไงตามเวลา — สำคัญที่สุดสำหรับระบบเทรด |
| Drawdown chart | ติดลบจากจุดสูงสุดลึกแค่ไหน นานแค่ไหน |
| Return distribution | ผลตอบแทนกระจายตัวยังไง หางอ้วนไหม |
| Rolling volatility | ความผันผวนเปลี่ยนตามเวลายังไง |
| Correlation heatmap | อะไรไปด้วยกัน |

**Equity curve + drawdown คู่กัน** — มาตรฐานของการรายงานผลระบบเทรด
```python
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8),
                               sharex=True, height_ratios=[2, 1])
ax1.plot(equity.index, equity.values)
ax1.set_ylabel("ทุน (USD)")
ax1.set_yscale("log")        # log scale — จำเป็นเมื่อทุนโตหลายเท่า

ax2.fill_between(dd.index, dd.values, 0, alpha=0.4, color="crimson")
ax2.set_ylabel("Drawdown (%)")
```

> ทำไมต้อง log scale: กำไร 100% จาก $100 เป็น $200 กับจาก $10,000 เป็น $20,000
> เป็นผลงานเท่ากัน แต่บนแกนปกติอันหลังดูใหญ่กว่า 100 เท่า
> แกน log ทำให้เปอร์เซ็นต์เท่ากันมีระยะเท่ากัน — นี่คือวิธีดู equity curve ที่ถูกต้อง

### ฝึก (3 ชม.)
1. Correlation heatmap 20 เหรียญ ใช้ colormap ให้ถูก
2. Candlestick BTC 6 เดือนล่าสุด + volume ข้างล่าง
3. Equity curve + drawdown ของกลยุทธ์ buy & hold BTC (log scale)
4. Box plot ผลตอบแทนรายวันแยกตามวันในสัปดาห์ — เห็นอะไรไหม
   (เก็บคำถามนี้ไว้ทดสอบจริงใน Sprint 7)

---

## สัปดาห์ 21 — โปรเจกต์ส่ง

### โปรเจกต์ — Visual Story (5 ชม.)

**เป้าหมายไม่ใช่ "วาดกราฟ 6 อัน" แต่คือ "เล่าเรื่องหนึ่งเรื่องด้วยกราฟ 6 อัน"**

เลือกคำถามหลักหนึ่งข้อ เช่น:
- "การกระจายพอร์ตไปหลายเหรียญช่วยลดความเสี่ยงจริงไหม"
- "ตลาดคริปโตเปลี่ยนพฤติกรรมไปจากปี 2018 แค่ไหน"
- "altcoin ตามหลัง BTC จริงตามที่คนพูดกันไหม"

สร้าง `bootcamp/sprint06/story.ipynb` ที่:

1. **เปิดด้วยคำถาม** — 1 ย่อหน้า ว่าจะตอบอะไร ทำไมถึงสำคัญ
2. **กราฟ 6 อัน เรียงลำดับให้เป็นเรื่องเล่า** แต่ละอันต้อง:
   - มีชื่อกราฟที่เป็นข้อสรุป
   - มีย่อหน้าใต้กราฟอธิบายว่าเห็นอะไรและมันแปลว่าอะไร
   - ใช้กราฟคนละชนิดกันอย่างน้อย 4 ชนิด
   - มีอย่างน้อย 1 อันเป็น interactive (plotly)
3. **ปิดด้วยคำตอบ** — ตอบคำถามที่ตั้งไว้ พร้อมระบุความมั่นใจและข้อจำกัด
4. **ส่วน "สิ่งที่กราฟนี้อาจหลอกเรา"** — เขียนอย่างน้อย 2 ข้อ เช่น
   ช่วงเวลาที่เลือกมีผลต่อข้อสรุปไหม, survivorship bias (เหรียญที่ตายไปแล้วไม่อยู่ในข้อมูล)

**ข้อกำหนดคุณภาพ**
- ทุกกราฟมีชื่อแกนพร้อมหน่วย
- ไม่มีกราฟวงกลม
- สีที่ใช้ต้องแยกออกได้แม้พิมพ์ขาวดำ หรือใช้ colorblind-safe palette
- export กราฟทั้งหมดเป็น PNG เก็บใน `charts/`

**เกณฑ์ผ่าน:** คนอ่านที่ไม่รู้เรื่องคริปโตเลย อ่านจบแล้วเข้าใจคำตอบและรู้ว่าเชื่อได้แค่ไหน

---

## Checkpoint

1. เมื่อไหร่ใช้ bar เมื่อไหร่ใช้ line และทำไมแกน y ของ bar ต้องเริ่มที่ 0
2. `fig` กับ `ax` ใน matplotlib ต่างกันยังไง
3. ทำไม correlation heatmap ต้องใช้ diverging colormap
4. ทำไม equity curve ควรใช้แกน log
5. ยกตัวอย่างกราฟที่ถูกต้องทางเทคนิคทุกอย่าง แต่ทำให้คนอ่านเข้าใจผิดได้

---

**ต่อไป:** [Sprint 7 — Statistics for Data Analyst](sprint-07-statistics.md)
