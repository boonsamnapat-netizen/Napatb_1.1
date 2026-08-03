# Sprint 2 — SQL & Database Design

**สัปดาห์ 4–7 · ~20 ชม. · เครื่องมือ: SQLite (DB Browser หรือ sqliteonline.com)**

---

## ทำไม SQL ยังสำคัญในปี 2026

เพราะข้อมูลขององค์กรเกือบทั้งหมดอยู่ในฐานข้อมูล และ SQL คือภาษาเดียวที่ทุกฐานข้อมูลพูดได้
ประกาศรับสมัคร data analyst แทบทุกใบขอ SQL — บางใบไม่ขอ Python ด้วยซ้ำ

อีกเหตุผลที่สำคัญกว่า: SQL บังคับให้คุณคิดเป็น **เซ็ตของข้อมูล** ไม่ใช่ทีละแถว
ซึ่งเป็นวิธีคิดเดียวกับที่ทำให้โค้ด pandas เร็วและอ่านง่ายใน Sprint 5

---

## สัปดาห์ 4 — SELECT และการกรอง

### เรียน (2 ชม.)

**ลำดับการเขียน vs ลำดับการทำงาน** — เรื่องนี้อธิบาย error งง ๆ ได้ 80%

```sql
SELECT   symbol, AVG(close) AS avg_close   -- เขียนอันดับ 1, ทำอันดับ 5
FROM     prices                            -- เขียน 2, ทำ 1
WHERE    date >= '2024-01-01'              -- เขียน 3, ทำ 2
GROUP BY symbol                            -- เขียน 4, ทำ 3
HAVING   AVG(close) > 100                  -- เขียน 5, ทำ 4
ORDER BY avg_close DESC                    -- เขียน 6, ทำ 6
LIMIT    10;                               -- เขียน 7, ทำ 7
```

เพราะ `SELECT` ทำงานเกือบท้ายสุด → **ใช้ alias ที่ตั้งใน SELECT ในส่วน WHERE ไม่ได้**
(แต่ใช้ใน `ORDER BY` ได้ เพราะมันทำงานทีหลัง) นี่คือ error ที่มือใหม่เจอบ่อยที่สุด

**คำสั่งพื้นฐาน**
```sql
SELECT * FROM prices LIMIT 5;
SELECT DISTINCT symbol FROM prices;
SELECT symbol, close FROM prices WHERE close > 50000;
SELECT * FROM prices WHERE symbol IN ('BTCUSDT','ETHUSDT');
SELECT * FROM prices WHERE date BETWEEN '2024-01-01' AND '2024-12-31';
SELECT * FROM prices WHERE symbol LIKE '%USDT';
SELECT * FROM prices WHERE volume IS NULL;
```

⚠️ `NULL` ไม่ใช่ 0 และไม่ใช่ค่าว่าง มันคือ "ไม่รู้"
`WHERE volume = NULL` จะไม่คืนแถวไหนเลย ต้องใช้ `IS NULL` เสมอ
และ `NULL` ทำให้การคำนวณเป็น `NULL` ทั้งหมด — `5 + NULL = NULL`

**CASE WHEN** — `IF` ของ SQL
```sql
SELECT symbol, close,
  CASE WHEN close > open THEN 'up'
       WHEN close < open THEN 'down'
       ELSE 'flat' END AS direction
FROM prices;
```

### ฝึก (3 ชม.)
สร้างฐานข้อมูลจาก CSV ก่อน (DB Browser → File → Import → Table from CSV file)
นำเข้า BTCUSDT, ETHUSDT, SOLUSDT เป็น 3 ตาราง แล้วเขียน query ตอบ:
1. 20 วันที่ BTC ปิดสูงสุดตลอดกาล
2. จำนวนวันที่ ETH ปิดเขียว (close > open) ในปี 2024
3. เพิ่มคอลัมน์คำนวณ `range_pct` แล้วหา 10 วันผันผวนสุดของ SOL
4. วันไหนที่ทั้งสามเหรียญปิดแดงพร้อมกัน (ยังไม่ต้องใช้ JOIN — ลองคิดวิธีดูก่อน)

---

## สัปดาห์ 5 — GROUP BY, JOIN และการออกแบบตาราง

### เรียน (2 ชม.)

**Aggregate + GROUP BY**
```sql
SELECT strftime('%Y', date) AS yr,
       COUNT(*)                     AS n_days,
       AVG(close)                   AS avg_close,
       MAX(high)                    AS peak,
       SUM(volume)                  AS total_vol
FROM prices
GROUP BY yr
HAVING COUNT(*) > 300      -- ตัดปีที่ข้อมูลไม่ครบ
ORDER BY yr;
```

`WHERE` กรอง**ก่อน**จัดกลุ่ม, `HAVING` กรอง**หลัง**จัดกลุ่ม — จำง่าย ๆ ว่า
ถ้าเงื่อนไขมี aggregate function อยู่ ต้องใช้ `HAVING`

**JOIN 4 แบบ**

| แบบ | ได้อะไร | ใช้เมื่อไหร่ |
|---|---|---|
| `INNER JOIN` | เฉพาะที่ตรงกันทั้งสองฝั่ง | ต้องการข้อมูลครบทั้งคู่ |
| `LEFT JOIN` | ทุกแถวฝั่งซ้าย + ที่ตรงจากขวา (ไม่ตรง = NULL) | ไม่อยากเสียแถวจากตารางหลัก |
| `RIGHT JOIN` | กลับกัน (SQLite ไม่รองรับ — สลับข้างเอา) | นาน ๆ ใช้ที |
| `FULL OUTER` | ทุกแถวทั้งสองฝั่ง | หาว่าอะไรหายไปจากฝั่งไหน |

**JOIN กับข้อมูลราคาคือกับดัก:** ถ้า `INNER JOIN` BTC กับ SOL ด้วย `date`
คุณจะเหลือแค่ช่วงที่ SOL มีข้อมูล (SOL เริ่มปี 2020) แถวปี 2018–2019 ของ BTC หายหมด
บางทีนั่นคือสิ่งที่ต้องการ บางทีไม่ใช่ — **ต้องรู้ตัวว่าเลือกอะไร** ไม่ใช่บังเอิญได้

**การออกแบบตาราง — Star Schema**
- **Fact table** — ตารางเหตุการณ์ แถวเยอะ ตัวเลขเยอะ (เช่น `prices`, `trades`)
- **Dimension table** — ตารางคำอธิบาย แถวน้อย ข้อความเยอะ (เช่น `coins`, `dates`)

หลักการ: อย่าเก็บข้อมูลซ้ำ ถ้า "Bitcoin" ปรากฏ 3,000 แถวใน fact table
ให้เก็บแค่ `symbol_id` แล้วเก็บชื่อเต็มไว้ใน dimension table แถวเดียว

### ฝึก (3 ชม.)
1. รวม 3 ตารางเหรียญเป็นตารางเดียวชื่อ `prices` ที่มีคอลัมน์ `symbol` (ใช้ `UNION ALL`)
2. `JOIN` ตาราง BTC กับ ETH ด้วย `date` แล้วหาวันที่ BTC เขียวแต่ ETH แดง
3. ลอง `INNER` แล้วเทียบกับ `LEFT` — นับแถวทั้งสองแบบ อธิบายว่าทำไมต่างกัน
4. สร้าง dimension table `coins(symbol, full_name, category, launch_year)` แล้ว join กลับ

---

## สัปดาห์ 6 — Subquery, CTE และ Window Function

### เรียน (2 ชม.)

**CTE (`WITH`)** — ตั้งชื่อให้ query ย่อย ทำให้อ่านง่ายกว่า subquery ซ้อนกันมาก
```sql
WITH daily AS (
  SELECT date, symbol, close,
         LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS prev_close
  FROM prices
),
returns AS (
  SELECT *, (close - prev_close) / prev_close * 100 AS change_pct
  FROM daily WHERE prev_close IS NOT NULL
)
SELECT symbol, AVG(change_pct), COUNT(*) FROM returns GROUP BY symbol;
```

**Window function** — เครื่องมือที่ทรงพลังที่สุดใน SQL สมัยใหม่
ต่างจาก `GROUP BY` ตรงที่ **ไม่ยุบแถว** — คำนวณค่าสรุปแต่ยังเห็นทุกแถว

| ฟังก์ชัน | ทำอะไร |
|---|---|
| `LAG(x, n)` | ค่าของ n แถวก่อนหน้า — ใช้คำนวณผลตอบแทน |
| `LEAD(x, n)` | ค่าของ n แถวถัดไป — ⚠️ ระวัง! อ่านคำเตือนข้างล่าง |
| `ROW_NUMBER()` | ลำดับที่ |
| `RANK()` / `DENSE_RANK()` | อันดับ (ต่างกันตอนคะแนนเท่ากัน) |
| `AVG(x) OVER (...)` | ค่าเฉลี่ยเคลื่อนที่ |

```sql
-- Moving average 20 วัน
SELECT date, close,
       AVG(close) OVER (PARTITION BY symbol ORDER BY date
                        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ma20
FROM prices;
```

> 🚨 **คำเตือนที่จะเข้าใจเต็ม ๆ ใน Sprint 9**
> `LEAD()` ดึงข้อมูล**อนาคต**มาใส่แถวปัจจุบัน ถ้าคุณเผลอเอาคอลัมน์นั้นไปเป็น
> feature ของโมเดล = โมเดลเห็นอนาคต = accuracy สวยงามและไร้ค่าโดยสิ้นเชิง
> อันนี้คือ **data leakage** สาเหตุอันดับหนึ่งที่ระบบเทรดกำไรใน backtest แต่ขาดจริง
> `LEAD()` ใช้ได้ที่เดียวคือสร้าง **label/target** (สิ่งที่จะทำนาย) ไม่ใช่ feature

### ฝึก (3 ชม.)
1. คำนวณผลตอบแทนรายวันของทุกเหรียญด้วย `LAG` ใน CTE
2. สร้าง MA20 และ MA50 แล้วหาวันที่ MA20 ตัดขึ้นเหนือ MA50 (golden cross)
3. ใช้ `RANK()` หาว่าแต่ละปี เหรียญไหนให้ผลตอบแทนดีที่สุด
4. หา drawdown: ระยะห่างจากจุดสูงสุดที่เคยทำได้ (hint: `MAX(close) OVER (ORDER BY date ROWS UNBOUNDED PRECEDING)`)

---

## สัปดาห์ 7 — โปรเจกต์ส่ง

### โปรเจกต์ — Crypto Market Database (5 ชม.)

**ส่วนที่ 1: ออกแบบและสร้าง**

สร้างไฟล์ `bootcamp/sprint02/crypto.db` ที่มี:

| ตาราง | ชนิด | เนื้อหา |
|---|---|---|
| `coins` | dimension | `symbol` (PK), `full_name`, `category`, `launch_year` |
| `dates` | dimension | `date` (PK), `year`, `month`, `day_of_week`, `is_weekend` |
| `prices` | fact | `date`, `symbol`, `open`, `high`, `low`, `close`, `volume` (PK ผสม) |
| `signals` | fact | `date`, `symbol`, `signal_type`, `direction` (สร้างจากกฎง่าย ๆ เช่น golden cross) |

ต้องมี: primary key ทุกตาราง, foreign key จาก fact ไป dimension, index บน `prices(date)`
เขียน DDL ทั้งหมดเก็บไว้ในไฟล์ `schema.sql`

**ส่วนที่ 2: ER diagram**
วาดผังความสัมพันธ์ (ใช้ [dbdiagram.io](https://dbdiagram.io/) หรือวาดมือถ่ายรูปก็ได้)
บันทึกเป็น `er-diagram.png`

**ส่วนที่ 3: 10 คำถามธุรกิจ**
เขียนไฟล์ `queries.sql` ตอบคำถามพวกนี้ พร้อมคอมเมนต์อธิบายแต่ละอัน:

1. เหรียญไหนผันผวนที่สุด วัดด้วยส่วนเบี่ยงเบนมาตรฐานของผลตอบแทนรายวัน
2. ปีไหนที่ตลาดโดยรวมแย่ที่สุด และแย่แค่ไหน
3. เหรียญไหนมีวันที่ปริมาณซื้อขายพุ่งเกิน 3 เท่าของค่าเฉลี่ย 20 วัน บ่อยที่สุด
4. Drawdown ลึกสุดของแต่ละเหรียญคือเท่าไหร่ เกิดวันไหน
5. เมื่อ BTC ลงเกิน 5% ในหนึ่งวัน altcoin ลงเฉลี่ยกี่ %
6. วันไหนของสัปดาห์ที่ผลตอบแทนเฉลี่ยดีที่สุด แยกตามเหรียญ
7. สัญญาณ golden cross ในตาราง `signals` ตามมาด้วยผลตอบแทน 7 วันเฉลี่ยเท่าไหร่
8. เหรียญคู่ไหนที่ขึ้นลงพร้อมกันบ่อยที่สุด (นับวันที่ทิศทางตรงกัน)
9. มีวันที่ข้อมูลหายไหม แต่ละเหรียญหายกี่วัน (hint: เทียบกับตาราง `dates`)
10. ถ้าซื้อถือตั้งแต่วันแรกที่มีข้อมูลจนวันสุดท้าย แต่ละเหรียญได้กี่ %

**ส่วนที่ 4: `findings.md`**
สรุปสิ่งที่พบจาก 10 ข้อ พร้อมระบุว่าข้อไหนที่คำตอบ**เชื่อไม่ได้** และเพราะอะไร

ข้อ 7 คือกับดักที่ตั้งใจวางไว้ — golden cross ในข้อมูลชุดนี้อาจดูดีมาก
แต่คุณกำลังดูข้อมูลชุดเดียวกับที่ใช้ตั้งกฎ Sprint 9 จะสอนว่าทำไมนั่นถึงไม่นับ

**เกณฑ์ผ่าน:** schema มี PK/FK ครบ, ทุก query รันผ่านและให้คำตอบที่สมเหตุสมผล,
`findings.md` ระบุข้อจำกัดของอย่างน้อย 2 ข้อ

---

## Checkpoint

1. ทำไมใช้ alias จาก `SELECT` ใน `WHERE` ไม่ได้ แต่ใช้ใน `ORDER BY` ได้
2. `WHERE` กับ `HAVING` ต่างกันยังไง ยกตัวอย่างที่ใช้ `HAVING` แทน `WHERE` ไม่ได้
3. `INNER JOIN` ข้อมูลราคา BTC (2018–) กับ SOL (2020–) จะได้กี่แถว เทียบกับ `LEFT JOIN` จาก BTC
4. เขียน query คำนวณ MA20 ด้วย window function จากความจำ
5. ทำไม `LEAD()` ถึงอันตรายเมื่อใช้สร้าง feature ของโมเดล

---

**ต่อไป:** [Sprint 3 — Python Foundation](sprint-03-python-foundation.md)
