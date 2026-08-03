# Sprint 4 — OOP, ไฟล์ และงานอัตโนมัติ

**สัปดาห์ 12–14 · ~15 ชม. · เครื่องมือ: VS Code (ย้ายจาก Colab), Git, GitHub**

---

## เป้าหมาย

sprint นี้เปลี่ยนคุณจาก "คนเขียนสคริปต์" เป็น "คนเขียนโปรแกรม"
สิ่งที่ต่างกันคือ: สคริปต์รันครั้งเดียวแล้วทิ้ง โปรแกรมมีคนกลับมาอ่านและแก้

จบ sprint นี้คุณจะอ่านโครงสร้าง `src/signal/` ใน repo นี้ออก และรู้ว่าทำไมมันถูกแบ่งเป็นโมดูลแบบนั้น

---

## สัปดาห์ 12 — ย้ายมา VS Code + Git

### เรียน (2 ชม.)

**ทำไมต้องย้ายจาก Colab**
Colab ดีสำหรับทดลอง แต่โปรเจกต์จริงต้องการ: หลายไฟล์, version control, การรันจาก terminal,
และ debugger ที่หยุดดูค่าตัวแปรกลางทางได้

**ติดตั้ง**
1. [VS Code](https://code.visualstudio.com/) + extension: Python, Jupyter, GitLens
2. Python 3.11+ จาก [python.org](https://www.python.org/) (Windows: ติ๊ก "Add to PATH" ด้วย)
3. ตรวจสอบ: `python --version` ใน terminal

**Virtual environment — ทำทุกโปรเจกต์เสมอ**
```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install pandas matplotlib
pip freeze > requirements.txt
```
เหตุผล: โปรเจกต์ A ต้องการ pandas 1.5 โปรเจกต์ B ต้องการ 2.1
ถ้าลงรวมกันในเครื่อง อันหนึ่งจะพัง venv คือการแยกกล่องให้แต่ละโปรเจกต์

**Git — 8 คำสั่งที่ใช้ 95% ของเวลา**
```bash
git status                    # ตอนนี้มีอะไรเปลี่ยนบ้าง — ใช้บ่อยที่สุด
git add <file>                # เลือกไฟล์ที่จะบันทึก
git commit -m "ข้อความ"        # บันทึกจุดกลับได้
git log --oneline             # ดูประวัติ
git diff                      # ดูว่าเปลี่ยนอะไรไปบ้าง
git checkout -b <branch>      # แตกกิ่งใหม่
git push -u origin <branch>   # ส่งขึ้น GitHub
git pull origin <branch>      # ดึงของใหม่ลงมา
```

**เขียน commit message ให้ดี**
```
❌ "update"  "fix"  "asdf"  "งานวันนี้"
✅ "add moving average function to indicators"
✅ "fix division by zero when entry equals stop"
```
กฎ: เขียนต่อจากประโยค "commit นี้จะ___" ให้ได้ความ

**`.gitignore`** — ห้าม commit: `.venv/`, `__pycache__/`, `.env`, ไฟล์ข้อมูลใหญ่ ๆ,
และ**ที่สำคัญที่สุดคือ API key และรหัสผ่าน** (repo นี้เก็บ token ไว้ใน GitHub Secrets ด้วยเหตุผลนี้)

### ฝึก (3 ชม.)
1. สร้าง repo ใหม่ชื่อ `data-bootcamp` บน GitHub แล้ว clone ลงเครื่อง
2. ย้ายโปรเจกต์ Sprint 1–3 เข้ามา commit แยกกัน
3. แตก branch ใหม่ แก้ไฟล์ commit แล้ว push
4. เปิดโปรเจกต์ Sprint 3 ใน VS Code แล้วลองใช้ debugger — ตั้ง breakpoint แล้วรันทีละบรรทัด

---

## สัปดาห์ 13 — อ่านเขียนไฟล์ + OOP

### เรียน (2 ชม.)

**อ่านไฟล์ให้ถูกวิธี**
```python
from pathlib import Path
import csv, json

data_dir = Path("data/real/crypto")           # ใช้ pathlib ไม่ใช่ string ต่อกัน
                                              # เพราะ Windows ใช้ \ แต่ Linux ใช้ /

with open(data_dir / "BTCUSDT.csv", encoding="utf-8") as f:
    reader = csv.DictReader(f)                # ได้ dict ต่อแถว ใช้ชื่อคอลัมน์ได้เลย
    rows = [row for row in reader]

print(rows[0])   # {'Date': '2018-01-01', 'Open': '14112.20', ...}
```

⚠️ **ทุกค่าที่อ่านจาก CSV เป็น string** `rows[0]["Close"]` คือ `'13657.2'` ไม่ใช่ตัวเลข
`'13657.2' > '9000'` จะได้ `False` เพราะเทียบทีละตัวอักษร ('1' < '9')
บั๊กนี้เงียบมาก ต้องแปลงชนิดเองเสมอ: `float(row["Close"])`

**เดินทั้งโฟลเดอร์**
```python
for csv_file in sorted(data_dir.glob("*.csv")):
    symbol = csv_file.stem          # 'BTCUSDT'
    print(f"processing {symbol}")
```

**JSON** — ใช้เก็บ config และผลลัพธ์
```python
with open("result.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)   # ensure_ascii=False เพื่อให้ภาษาไทยอ่านออก
```

**OOP — คลาสคืออะไรและใช้เมื่อไหร่**

ใช้คลาสเมื่อคุณมี **ข้อมูลที่ผูกกับพฤติกรรม** และมีหลายชุด
ถ้ามีแค่ฟังก์ชันคำนวณเดี่ยว ๆ อย่าสร้างคลาส — ฟังก์ชันธรรมดาดีกว่า

```python
class Position:
    def __init__(self, symbol: str, entry: float, stop: float, size: float):
        self.symbol = symbol
        self.entry  = entry
        self.stop   = stop
        self.size   = size

    @property                                  # เรียกแบบ attribute ไม่ต้องใส่วงเล็บ
    def risk_usd(self) -> float:
        return abs(self.entry - self.stop) * self.size

    def pnl_at(self, price: float) -> float:
        return (price - self.entry) * self.size

    def r_multiple(self, price: float) -> float:
        return self.pnl_at(price) / self.risk_usd

    def __repr__(self) -> str:                 # ทำให้ print(pos) อ่านรู้เรื่อง
        return f"Position({self.symbol} @ {self.entry:,.2f}, size={self.size:.4f})"
```

**`dataclass`** — ทางลัดสำหรับคลาสที่เก็บข้อมูลเป็นหลัก
```python
from dataclasses import dataclass

@dataclass
class Signal:
    symbol: str
    date: str
    direction: str
    entry: float
    confidence: float = 0.5      # ค่า default

s = Signal("BTCUSDT", "2024-06-01", "long", 68500)
print(s)     # Signal(symbol='BTCUSDT', ...) — ได้ __init__ และ __repr__ ฟรี
```

### ฝึก (3 ชม.)
1. เขียนฟังก์ชันอ่าน CSV ทุกไฟล์ในโฟลเดอร์ คืน dict ที่ key คือ symbol
2. เขียนคลาส `Position` แบบข้างบนให้ครบ แล้วทดสอบทั้ง long และ short
3. เขียนคลาส `Portfolio` ที่เก็บหลาย `Position` มี method `total_risk()` และ `add()`
4. บันทึกผลลัพธ์เป็น JSON แล้วอ่านกลับมาสร้าง object ใหม่ให้ได้ค่าเดิม

---

## สัปดาห์ 14 — โปรเจกต์ส่ง

### โปรเจกต์ — CSV Scanner + Portfolio Tracker (5 ชม.)

สร้างโฟลเดอร์ `bootcamp/sprint04/` แบ่งเป็นหลายไฟล์:

```
sprint04/
├── loader.py        # อ่านและ validate ไฟล์ CSV
├── models.py        # คลาส Position, Portfolio
├── scan.py          # โปรแกรมหลักที่รันจาก command line
├── requirements.txt
└── README.md
```

**`loader.py`**
- `load_symbol(path) -> list[dict]` — อ่านไฟล์เดียว แปลงชนิดข้อมูลให้ถูก
  (`Date` เป็น `datetime`, ราคาเป็น `float`, `Volume` เป็น `int`)
- `load_all(dir) -> dict[str, list[dict]]` — อ่านทั้งโฟลเดอร์
- `validate(rows) -> list[str]` — คืนรายการปัญหาที่เจอ:
  วันซ้ำ, วันหาย, `High < Low`, ราคาติดลบ, `Volume = 0`, แถวที่มีค่าว่าง
- รองรับทั้ง `crypto/` (คอลัมน์ `Date`) และ `crypto_1h/` (คอลัมน์ `Datetime`)
  — ต้องตรวจจับเองว่าไฟล์เป็นแบบไหน อย่าให้ผู้ใช้ต้องบอก

**`models.py`**
- `Position` — ตามที่ฝึกมา + method `is_stopped_out(low, high)` ที่ทำงานถูกทั้ง long/short
- `Portfolio` — เก็บหลาย position, มี `total_risk_usd`, `total_risk_pct(balance)`,
  `by_direction()` (นับ long/short), และ `heat_check(max_pct)` ที่เตือนเมื่อความเสี่ยงรวมเกิน

**`scan.py`** — รันได้จาก terminal
```bash
python scan.py --data-dir data/real/crypto
python scan.py --data-dir data/real/crypto --symbol BTCUSDT --verbose
python scan.py --data-dir data/real/crypto --output report.json
```
ใช้ `argparse` (ไลบรารีมาตรฐาน) แสดงผล: จำนวนไฟล์, ช่วงวันที่, ปัญหาที่เจอต่อไฟล์,
และตารางสรุปผลตอบแทนรวมของแต่ละเหรียญ

**`README.md`** — อธิบายวิธีใช้ + สิ่งที่ค้นพบจากการ validate
(เช่น เหรียญไหนข้อมูลหายบ้าง หายกี่วัน)

**ข้อกำหนด**
- ทุกไฟล์ import กันได้ ไม่มี circular import
- `scan.py` เท่านั้นที่มี `print` — ไฟล์อื่นคืนค่ากลับมา
- commit อย่างน้อย 5 ครั้ง แต่ละครั้งมี message ที่สื่อความ
- push ขึ้น GitHub

**เกณฑ์ผ่าน:** รันคำสั่งทั้ง 3 แบบข้างบนได้, `validate()` ตรวจเจอปัญหาจริงในข้อมูล
(มีแน่นอน — ข้อมูลจริงไม่เคยสะอาด), โครงสร้างไฟล์แยกหน้าที่ชัดเจน

### อ่านโค้ดจริง (โบนัส 1 ชม.)
เปิด `src/signal/money_management.py` และ `src/signal/portfolio.py` ใน repo นี้
เทียบกับที่คุณเพิ่งเขียน — หา 3 อย่างที่เขาทำต่างจากคุณ และคิดว่าทำไม

---

## Checkpoint

1. ทำไมต้องใช้ virtual environment แยกแต่ละโปรเจกต์
2. อ่าน CSV แล้วได้ `'13657.2' > '9000'` เป็น `False` — อธิบายว่าทำไม
3. เมื่อไหร่ควรใช้ class เมื่อไหร่ควรใช้แค่ function
4. `@property` ทำอะไร ต่างจาก method ธรรมดายังไง
5. อะไรบ้างที่ห้าม commit ขึ้น git เด็ดขาด และเพราะอะไร

---

**ต่อไป:** [Sprint 5 — Data Transformation ด้วย pandas](sprint-05-pandas.md)
