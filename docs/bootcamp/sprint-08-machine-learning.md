# Sprint 8 — Machine Learning เบื้องต้น

**สัปดาห์ 25–27 · ~15 ชม. · เครื่องมือ: scikit-learn**

---

## เป้าหมายและคำเตือน

sprint นี้สอนให้สร้างโมเดล ML คลาสสิกเป็น: regression, classification, clustering

**คำเตือนตั้งแต่บรรทัดนี้:** ทุกอย่างที่คุณสร้างใน sprint นี้จะให้ผลลัพธ์ที่**ดูดีเกินจริง**
เพราะเราจะยังใช้วิธีแบ่งข้อมูลแบบมาตรฐานซึ่ง**ผิด**สำหรับข้อมูลอนุกรมเวลา

นั่นเป็นความตั้งใจ — Sprint 9 จะรื้อทุกอย่างในนี้แล้วทำใหม่ให้ถูก
การได้เห็นตัวเลขสวย ๆ ก่อน แล้วค่อยเห็นมันพังตอนทำถูก เป็นบทเรียนที่จำได้นานกว่าการอ่าน

---

## สัปดาห์ 25 — แนวคิดและ Regression

### เรียน (2 ชม.)

**ML คืออะไร** — หาความสัมพันธ์จากข้อมูลแทนการเขียนกฎเอง

| ประเภท | มี label ไหม | ทำอะไร | ตัวอย่าง |
|---|---|---|---|
| Supervised — regression | มี | ทำนายตัวเลข | ทำนายราคาพรุ่งนี้ |
| Supervised — classification | มี | ทำนายหมวด | ขึ้นหรือลง |
| Unsupervised — clustering | ไม่มี | จัดกลุ่ม | จัดกลุ่มเหรียญตามพฤติกรรม |
| Unsupervised — dim. reduction | ไม่มี | ลดมิติ | PCA |

**คำศัพท์**
- **Feature (X)** — ตัวแปรที่ใช้ทำนาย
- **Target (y)** — สิ่งที่จะทำนาย
- **Underfitting** — โมเดลง่ายเกิน ทำนายแย่ทั้ง train และ test
- **Overfitting** — โมเดลจำข้อมูลฝึกได้ แต่ใช้กับข้อมูลใหม่ไม่ได้
- **Bias-variance tradeoff** — โมเดลง่าย = bias สูง, โมเดลซับซ้อน = variance สูง

**Overfitting คือศัตรูอันดับหนึ่งในข้อมูลการเงิน** เพราะสัญญาณจริงอ่อนมาก
เสียงรบกวนเยอะมาก โมเดลที่ซับซ้อนพอจะจำเสียงรบกวนได้เสมอ

**Workflow มาตรฐาน**
```python
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score

X = df[["ma20", "rsi", "atr14", "volume_ratio"]]
y = df["next_return"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42)     # 🚨 ผิดสำหรับ time series — Sprint 9

model = LinearRegression().fit(X_train, y_train)
pred = model.predict(X_test)
print(f"MAE {mean_absolute_error(y_test, pred):.4f}  R² {r2_score(y_test, pred):.4f}")
```

> 🚨 `train_test_split` แบบสุ่มจะเอาข้อมูลวันที่ 2024 ไปฝึก แล้วทดสอบกับวันที่ 2020
> = โมเดลเห็นอนาคตแล้วทำนายอดีต ผลที่ได้ไม่มีความหมายเลย
> ใช้ในสัปดาห์นี้เพื่อเรียน API ของ sklearn เท่านั้น

**โมเดล regression**
```python
from sklearn.linear_model import LinearRegression, Ridge, Lasso
from sklearn.ensemble import RandomForestRegressor
```
- `Ridge` — ลงโทษสัมประสิทธิ์ใหญ่ (L2) กัน overfit
- `Lasso` — ลงโทษแบบ L1 ตัดฟีเจอร์ที่ไม่จำเป็นเป็น 0 ให้เลย
- `RandomForest` — รวมต้นไม้หลายต้น จับความสัมพันธ์ไม่เชิงเส้นได้

**Metrics ของ regression**

| Metric | ความหมาย | ข้อสังเกต |
|---|---|---|
| MAE | ค่าคลาดเคลื่อนเฉลี่ย | ตีความง่าย ทนต่อ outlier |
| RMSE | ลงโทษความผิดพลาดใหญ่ | ไวต่อ outlier |
| R² | อธิบายความแปรปรวนได้กี่ % | **ในการทำนายผลตอบแทน R² 0.02 ก็ถือว่าดีมากแล้ว** |

ถ้าได้ R² = 0.9 ในการทำนายผลตอบแทนรายวัน — **มี leakage แน่นอน** ไปหาว่าอยู่ตรงไหน

### ฝึก (3 ชม.)
1. สร้างชุด feature จากข้อมูล BTC: MA ratio, RSI, ATR%, volume ratio, ผลตอบแทน 1/3/5 วันย้อนหลัง
2. ทำนายผลตอบแทนวันถัดไปด้วย LinearRegression ดู R²
3. เทียบ Ridge, Lasso, RandomForest — อันไหนดีกว่า
4. ดูสัมประสิทธิ์ของ Lasso ว่าตัดฟีเจอร์ไหนทิ้ง — ตรงกับที่คุณคาดไหม

---

## สัปดาห์ 26 — Classification และ Clustering

### เรียน (2 ชม.)

**Classification — ทำนายทิศทางง่ายกว่าทำนายราคา**
```python
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, confusion_matrix,
                             classification_report, roc_auc_score)

y = (df.Close.shift(-1) > df.Close).astype(int)     # 1 = พรุ่งนี้ขึ้น
```

**Metrics ของ classification — accuracy อย่างเดียวไม่พอ**

|  | ทำนายขึ้น | ทำนายลง |
|---|---|---|
| **จริงขึ้น** | TP | FN |
| **จริงลง** | FP | TN |

- **Precision** = `TP/(TP+FP)` — เวลาบอกว่าขึ้น ถูกกี่ %
- **Recall** = `TP/(TP+FN)` — วันที่ขึ้นจริง จับได้กี่ %
- **F1** — ค่าเฉลี่ยฮาร์มอนิกของสองอัน
- **ROC-AUC** — ความสามารถแยกแยะโดยรวม 0.5 = เดาสุ่ม

**สำหรับระบบเทรด precision สำคัญกว่า recall มาก**
พลาดโอกาส (recall ต่ำ) = ไม่ได้กำไร
ทำนายผิด (precision ต่ำ) = เสียเงินจริง
โมเดลที่ให้สัญญาณน้อยแต่แม่น มีค่ากว่าโมเดลที่ให้สัญญาณเยอะแต่มั่ว

**ข้อมูลไม่สมดุล** — ถ้า 53% ของวันเป็นวันเขียว โมเดลที่ทายว่า "ขึ้น" ทุกวัน
จะได้ accuracy 53% ทันที **ต้องเทียบกับ baseline นี้เสมอ**
```python
baseline = max(y.mean(), 1 - y.mean())
print(f"baseline {baseline:.2%} vs model {accuracy_score(y_test, pred):.2%}")
```
ถ้าโมเดลได้ 54% กับ baseline 53% — คุณยังไม่มีอะไรเลย

**Feature scaling**
```python
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

pipe = Pipeline([
    ("scaler", StandardScaler()),
    ("model", LogisticRegression()),
])
```
โมเดลที่ต้อง scale: Logistic Regression, SVM, KNN, Neural Network
โมเดลที่ไม่ต้อง: Decision Tree, Random Forest, Gradient Boosting

🚨 **ต้อง fit scaler กับ train เท่านั้น** แล้ว transform ทั้งสองชุด
ถ้า `fit` กับข้อมูลทั้งหมด = ค่าเฉลี่ยและ SD มาจากข้อมูล test ด้วย = leakage
`Pipeline` จัดการเรื่องนี้ให้อัตโนมัติ — นี่คือเหตุผลหลักที่ควรใช้ Pipeline เสมอ

**Clustering**
```python
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA

feats = returns.T          # แถวละเหรียญ
labels = KMeans(n_clusters=4, n_init=10).fit_predict(StandardScaler().fit_transform(feats))
```
ใช้จัดกลุ่มเหรียญที่พฤติกรรมคล้ายกัน — มีประโยชน์จริงกับการกระจายความเสี่ยง
เพราะการถือ 5 เหรียญจากคลัสเตอร์เดียวกัน ไม่ใช่การกระจายความเสี่ยง

**Feature importance**
```python
importances = pd.Series(rf.feature_importances_, index=X.columns).sort_values()
```
⚠️ `feature_importances_` ของ tree เอนเอียงไปทางฟีเจอร์ที่มีค่าหลากหลาย
ใช้ `permutation_importance` จะน่าเชื่อกว่า

### ฝึก (3 ชม.)
1. ทำนายทิศทางพรุ่งนี้ด้วย RandomForestClassifier — เทียบกับ baseline เสมอ
2. ดู confusion matrix และ precision/recall แยกกัน
3. ปรับ threshold จาก 0.5 เป็น 0.6 แล้วดูว่า precision เพิ่มไหม สัญญาณลดลงเท่าไหร่
4. Clustering 20 เหรียญด้วย KMeans + PCA แล้ววาดกราฟ 2 มิติ ตั้งชื่อแต่ละคลัสเตอร์

---

## สัปดาห์ 27 — โปรเจกต์ส่ง

### โปรเจกต์ — Direction Prediction Model (5 ชม.)

สร้าง `bootcamp/sprint08/model.ipynb`

**ส่วนที่ 1: Feature engineering**
สร้างอย่างน้อย 12 features จากข้อมูล OHLCV แบ่งเป็นกลุ่ม:
- **แนวโน้ม** — ratio ราคาต่อ MA20/MA50/MA200, ความชันของ MA
- **โมเมนตัม** — RSI, ผลตอบแทน 1/3/5/10 วันย้อนหลัง, MACD histogram
- **ความผันผวน** — ATR%, SD ของผลตอบแทน 20 วัน, Bollinger width
- **ปริมาณ** — volume ratio ต่อ MA20, OBV
- **บริบท** — ผลตอบแทน BTC (สำหรับ altcoin), วันในสัปดาห์

**บังคับ: ทำ leakage audit** — ตารางที่มีทุก feature พร้อมคอลัมน์
"ค่านี้รู้ได้ตอนไหน" ต้องเป็น "สิ้นวัน t" ทุกอัน ถ้ามีอันไหนต้องรอถึงวัน t+1 = ตัดทิ้ง

**ส่วนที่ 2: Target**
`y = 1` ถ้าผลตอบแทนวันถัดไป > 0
ลองอีกแบบ: `y = 1` ถ้าผลตอบแทน > +1% (กรองสัญญาณอ่อนออก) แล้วเทียบผล

**ส่วนที่ 3: โมเดล**
ฝึกอย่างน้อย 4 โมเดล: LogisticRegression, DecisionTree, RandomForest, GradientBoosting
ทุกอันใส่ใน `Pipeline` พร้อม scaler ตามเหมาะสม

**ส่วนที่ 4: ประเมินผล**
ตารางเทียบทุกโมเดล: accuracy, precision, recall, F1, ROC-AUC, **และ baseline**
พร้อม confusion matrix ของโมเดลที่ดีที่สุด

**ส่วนที่ 5: ตีความ**
- Feature importance (ใช้ permutation importance)
- 3 feature ที่สำคัญที่สุด — สมเหตุสมผลไหมในเชิงตลาด หรือแค่ noise
- ปรับ threshold แล้วดูเส้น precision-recall tradeoff

**ส่วนที่ 6 (สำคัญที่สุด): `doubts.md`**
เขียนรายการสิ่งที่คุณ**สงสัยว่าผลนี้เชื่อไม่ได้**:
- ผลนี้ดีกว่า baseline เท่าไหร่ ต่างกันอย่างมีนัยสำคัญไหม (ใช้สถิติจาก Sprint 7)
- `train_test_split` แบบสุ่มสร้างปัญหาอะไร อธิบายด้วยตัวเอง
- ถ้าเทรดตามโมเดลนี้ หักค่าธรรมเนียม 0.1% ต่อรอบ ยังเหลืออะไรไหม
- feature ไหนที่คุณไม่แน่ใจว่ามี leakage

**เกณฑ์ผ่าน:** ทุกโมเดลเทียบกับ baseline, มี leakage audit,
`doubts.md` ระบุปัญหาได้อย่างน้อย 3 ข้อ

> เก็บ notebook นี้ไว้ให้ดี **Sprint 9 จะเอามารื้อทำใหม่** แล้วคุณจะได้เห็นว่า
> ตัวเลขที่ได้วันนี้ เหลือเท่าไหร่เมื่อประเมินอย่างถูกต้อง

---

## Checkpoint

1. Overfitting กับ underfitting ต่างกันยังไง ดูจากอะไร
2. ทำไม accuracy อย่างเดียวไม่พอ และทำไม precision สำคัญกว่า recall ในระบบเทรด
3. baseline ของ classification คืออะไร คำนวณยังไง
4. ทำไมต้อง fit scaler กับ train set เท่านั้น
5. ถ้าโมเดลทำนายผลตอบแทนรายวันได้ R² = 0.85 คุณจะทำอะไรเป็นอย่างแรก

---

**ต่อไป:** [Sprint 9 — Validation, Leakage & Backtesting](sprint-09-validation.md)
