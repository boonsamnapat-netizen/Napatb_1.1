# ตัวกลางสำหรับ AI ดูรูปอาหาร (Cloudflare Worker)

เว็บแอปอยู่ใน repo สาธารณะ **ฝัง API key ลงไปไม่ได้** ใครก็เปิดอ่านได้
Worker ตัวนี้ทำหน้าที่ถือ key ไว้ฝั่งเซิร์ฟเวอร์ แอปยิงรูปมาที่นี่ แล้ว Worker ไปคุยกับ Claude แทน

```
แอปในมือถือ ──รูป──▶ Worker ของคุณ ──รูป + key──▶ Claude
                       (ถือ key ไว้)              │
              ◀── ชื่ออาหาร แคล มาโคร ◀───────────┘
```

Cloudflare Workers ฟรี 100,000 คำขอ/วัน — ใช้ส่วนตัวยังไงก็ไม่ถึง
ที่เสียเงินคือฝั่ง Anthropic ซึ่งคิดตามจำนวนรูป (ดูหัวข้อค่าใช้จ่ายท้ายไฟล์)

---

## สิ่งที่ต้องมีก่อน

- **Node.js** ในเครื่อง (พิมพ์ `node -v` ถ้าขึ้นเลขเวอร์ชัน = มีแล้ว ถ้าไม่ขึ้นโหลดจาก nodejs.org)
- **บัญชี Cloudflare** — สมัครฟรีที่ dash.cloudflare.com
- **API key ของ Anthropic** — สร้างที่ console.anthropic.com → Settings → API Keys (ต้องเติมเงินขั้นต่ำก่อน)

---

## ติดตั้ง

เปิด terminal แล้วเข้ามาที่โฟลเดอร์นี้

```bash
cd worker
npm install
npx wrangler login          # เปิดเบราว์เซอร์ให้กดอนุญาต
```

### ตั้งความลับ 2 ตัว

```bash
npx wrangler secret put ANTHROPIC_API_KEY
# วาง API key ของ Anthropic แล้ว Enter

npx wrangler secret put APP_TOKEN
# ตั้งรหัสอะไรก็ได้ที่เดายาก เช่น สุ่มมา 32 ตัวอักษร
# จำไว้ให้ดี ต้องเอาไปกรอกในแอปด้วย
```

> ทั้งสองตัวถูกเก็บฝั่ง Cloudflare ไม่ได้อยู่ในไฟล์ ไม่ขึ้น git

**สุ่มรหัส APP_TOKEN:** `node -e "console.log(require('crypto').randomBytes(24).toString('base64url'))"`

### ปล่อยขึ้นจริง

```bash
npx wrangler deploy
```

จะได้ URL หน้าตาแบบนี้กลับมา — **ก๊อปเก็บไว้**

```
https://tdee-food-vision.<ชื่อบัญชีคุณ>.workers.dev
```

---

## ต่อเข้ากับแอป

เปิดเว็บแอป → แท็บ **อาหาร** → **ตั้งค่า AI** แล้วกรอก 2 ช่อง

| ช่อง | ใส่อะไร |
|---|---|
| ที่อยู่ Worker | URL ที่ได้จาก `wrangler deploy` |
| รหัสแอป | `APP_TOKEN` ที่ตั้งไว้ |

กด **ทดสอบการเชื่อมต่อ** ถ้าเขียวคือใช้ได้ ค่าทั้งสองเก็บในเครื่องคุณ ไม่ขึ้น git

---

## ค่าใช้จ่าย

ตั้งต้นใช้ **Claude Opus 5** ($5 ต่อ 1 ล้าน token ขาเข้า / $25 ขาออก)
รูปหนึ่งที่ย่อแล้ว ~900px กินราว 1,300 token ขาเข้า + คำตอบราว 400 token ขาออก

**ตกราวรูปละ 0.5–0.7 บาท**

อยากให้ถูกลง แก้ `CLAUDE_MODEL` ใน `wrangler.toml` แล้ว deploy ใหม่:

| รุ่น | ราคา (เข้า/ออก ต่อ 1M token) | เหมาะกับ |
|---|---|---|
| `claude-opus-5` (ตั้งต้น) | $5 / $25 | ประเมินปริมาณอาหารแม่นสุด |
| `claude-sonnet-5` | $3 / $15 | ถูกลงพอควร ยังดีอยู่ |
| `claude-haiku-4-5` | $1 / $5 | ถูกสุด เร็วสุด แต่เดาปริมาณพลาดง่ายขึ้น |

ปรับ `EFFORT` ได้ด้วย (`low` / `medium` / `high`) — ยิ่งต่ำยิ่งถูกและเร็ว แต่คิดน้อยลง

> **ตั้งเพดานค่าใช้จ่ายไว้ด้วย** ที่ console.anthropic.com → Settings → Limits
> กันกรณี `APP_TOKEN` หลุดแล้วมีคนมายิงรัว ๆ

---

## แก้ปัญหา

| อาการ | สาเหตุ |
|---|---|
| `รหัสแอปไม่ถูกต้อง` | `APP_TOKEN` ในแอปกับใน Worker ไม่ตรงกัน ตั้งใหม่ด้วย `wrangler secret put APP_TOKEN` |
| ติด CORS ในหน้า console | ที่อยู่เว็บไม่ตรงกับ `ALLOWED_ORIGINS` ใน `wrangler.toml` แก้แล้ว `npx wrangler deploy` ใหม่ |
| `API key ของ Anthropic ไม่ถูกต้อง` | key ผิดหรือถูกเพิกถอน ตั้งใหม่ด้วย `wrangler secret put ANTHROPIC_API_KEY` |
| `รูปใหญ่เกินไป` | ปกติแอปย่อรูปให้แล้ว ถ้าเจอแปลว่าย่อไม่สำเร็จ ลองถ่ายใหม่ |
| ดูว่าเกิดอะไรขึ้นจริง | `npx wrangler tail` แล้วลองยิงจากแอป จะเห็น log สด |
