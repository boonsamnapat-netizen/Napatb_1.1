# vendor/

`zxing.min.js` — [@zxing/library](https://github.com/zxing-js/library) (Apache-2.0) build UMD ที่ไม่ได้แก้อะไร

ใช้อ่านบาร์โค้ดจากกล้องบนเครื่องที่ไม่มี `BarcodeDetector` — ซึ่งคือ **iPhone/iPad ทุกเครื่อง**
เพราะ Safari (และทุกเบราว์เซอร์บน iOS ที่ใช้ WebKit) ยังไม่รองรับ API ตัวนั้น

ไฟล์นี้ **ไม่ได้ถูกแคชตอนติดตั้งแอป** เพราะหนัก 362KB จะโหลดต่อเมื่อกดสแกนครั้งแรก
แล้ว service worker ค่อยเก็บไว้ให้ใช้ออฟไลน์รอบถัดไป
