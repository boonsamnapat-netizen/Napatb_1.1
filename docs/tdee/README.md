# งบแคลอรี่รายวัน — เว็บแอป TDEE

เว็บแอปหน้าเดียว ใช้งานได้ออฟไลน์ ติดตั้งลงหน้าจอโฮมได้ (PWA)
ข้อมูลทั้งหมดเก็บใน `localStorage` ของเบราว์เซอร์เครื่องนั้น ไม่มีการส่งออกไปที่ไหน

## เปิดให้เป็นเว็บจริง (ครั้งเดียวจบ)

GitHub → repo นี้ → **Settings → Pages**

- Source: **Deploy from a branch**
- Branch: **`claude/tdee-calculator-personal-7qoaz4`** · folder **`/docs`** → Save

รอสัก 1–2 นาที แล้วเปิด

    https://boonsamnapat-netizen.github.io/Napatb_1.1/tdee/

เปิดจากมือถือ → Chrome กด "ติดตั้งเป็นแอป" / Safari กดปุ่มแชร์ → "เพิ่มไปยังหน้าจอโฮม"

## ไฟล์

| ไฟล์ | หน้าที่ |
|---|---|
| `index.html` | โครงหน้า |
| `app.css` · `app.js` | สไตล์ และตรรกะทั้งหมด (คำนวณ TDEE, มาโคร, เทรนด์น้ำหนัก, กราฟ) |
| `pwa.js` | ปุ่มติดตั้ง, ลงทะเบียน service worker, แจ้งเวอร์ชันใหม่ |
| `sw.js` | แคชไฟล์ไว้ใช้ออฟไลน์ — **แก้ `VERSION` ทุกครั้งที่แก้ไฟล์อื่น** ไม่งั้นเครื่องที่ติดตั้งไว้จะยังเห็นของเก่า |
| `manifest.webmanifest` | ชื่อแอป ไอคอน สีธีม shortcut |
| `icon*.png` · `icon.svg` | ไอคอน (สร้างจาก `icon.svg`) |

## หน้า Artifact

`tools/tdee/index.html` คือไฟล์เดียวกันที่รวม CSS/JS เข้ามาไว้ในไฟล์เดียว สำหรับเผยแพร่เป็น Artifact
สร้างใหม่จากซอร์สในโฟลเดอร์นี้ด้วย

    python3 tools/tdee/build_artifact.py

อย่าแก้ `tools/tdee/index.html` ตรง ๆ — มันถูกเขียนทับทุกครั้งที่ build
