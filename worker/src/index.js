/**
 * tdee-food-vision — ตัวกลางระหว่างเว็บแอป "งบแคลอรี่รายวัน" กับ Claude
 *
 * มีอยู่เพราะเว็บแอปเป็นไฟล์นิ่งบน GitHub Pages ใน repo สาธารณะ
 * จะฝัง ANTHROPIC_API_KEY ลงไปตรง ๆ ไม่ได้ ใครก็เปิดอ่านได้
 * Worker ตัวนี้ถือ key ไว้ฝั่งเซิร์ฟเวอร์ แอปยิงมาที่นี่แทน
 *
 * POST /analyze
 *   headers: X-App-Token: <APP_TOKEN>
 *   body:    { "image": "<base64 ล้วน ไม่มี data: นำหน้า>",
 *              "media_type": "image/jpeg",
 *              "hint": "ข้อความใบ้ (ไม่บังคับ)" }
 *   → 200   { ok, name, items[], total{}, confidence, note }
 */

import Anthropic from "@anthropic-ai/sdk";

const MAX_IMAGE_BYTES = 5 * 1024 * 1024;          // ~3.7MB หลัง base64
const OK_MEDIA = ["image/jpeg", "image/png", "image/webp"];

const SYSTEM = `คุณคือนักกำหนดอาหารที่ชำนาญอาหารไทยเป็นพิเศษ หน้าที่คือดูรูปอาหารแล้วประเมินพลังงานและมาโครให้แม่นที่สุดเท่าที่รูปจะบอกได้

หลักการ:
- ตอบเป็นภาษาไทย ใช้ชื่ออาหารที่คนไทยเรียกจริง เช่น "ข้าวกะเพราไก่ไข่ดาว" ไม่ใช่ "ข้าวผัดใบโหระพา"
- แยกเป็นรายการย่อยเมื่อในรูปมีหลายอย่าง (ข้าว / กับข้าว / เครื่องดื่ม / ของทอด)
- ประเมินปริมาณจากสิ่งที่เทียบขนาดได้ในรูป — จาน ช้อน แก้ว มือ ถ้าไม่มีอะไรเทียบเลย ให้ถือว่าเป็นขนาดปกติที่ร้านไทยเสิร์ฟ
- อาหารไทยตามสั่งมักใช้น้ำมันและน้ำตาลมากกว่าที่ตาเห็น ผัดกะเพราจานหนึ่งใช้น้ำมันได้ถึง 2–3 ช้อนโต๊ะ อย่าประเมินต่ำเกินจริง
- ถ้ามีน้ำราด น้ำแกง หรือของทอด ให้บวกน้ำมันเข้าไปด้วย
- confidence ให้ตรงกับความจริง: high = เห็นชัดทั้งชนิดและปริมาณ, medium = รู้ว่าคืออะไรแต่เดาปริมาณ, low = รูปมืด/เห็นไม่ครบ/เดาส่วนผสมไม่ออก
- note ให้เขียนสั้น ๆ ว่าอะไรคือจุดที่ไม่แน่ใจและกระทบตัวเลขมากที่สุด เช่น "เดาปริมาณน้ำมันไม่ได้" หรือ "ไม่เห็นว่าข้าวเยอะแค่ไหน" ถ้ามั่นใจดีให้เขียนว่าอะไรที่ทำให้มั่นใจ
- ถ้ารูปไม่ใช่อาหาร ให้ ok = false แล้วใส่ 0 ทุกช่อง

ตัวเลขคือค่าประมาณเพื่อช่วยตัดสินใจ ไม่ใช่ค่าที่วัดมา — จุดที่พลาดง่ายที่สุดคือปริมาณ ไม่ใช่ชนิดอาหาร`;

const SCHEMA = {
  type: "object",
  properties: {
    ok: { type: "boolean" },
    name: { type: "string" },
    items: {
      type: "array",
      items: {
        type: "object",
        properties: {
          name:      { type: "string" },
          qty_desc:  { type: "string" },
          kcal:      { type: "number" },
          protein_g: { type: "number" },
          fat_g:     { type: "number" },
          carb_g:    { type: "number" }
        },
        required: ["name", "qty_desc", "kcal", "protein_g", "fat_g", "carb_g"],
        additionalProperties: false
      }
    },
    total: {
      type: "object",
      properties: {
        kcal:      { type: "number" },
        protein_g: { type: "number" },
        fat_g:     { type: "number" },
        carb_g:    { type: "number" }
      },
      required: ["kcal", "protein_g", "fat_g", "carb_g"],
      additionalProperties: false
    },
    confidence: { type: "string", enum: ["high", "medium", "low"] },
    note: { type: "string" }
  },
  required: ["ok", "name", "items", "total", "confidence", "note"],
  additionalProperties: false
};

function corsHeaders(origin, allowed) {
  const ok = origin && allowed.includes(origin);
  return {
    "Access-Control-Allow-Origin": ok ? origin : allowed[0] || "null",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-App-Token",
    "Access-Control-Max-Age": "86400",
    Vary: "Origin"
  };
}

const json = (body, status, headers) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { ...headers, "Content-Type": "application/json; charset=utf-8" }
  });

export default {
  async fetch(request, env) {
    const allowed = (env.ALLOWED_ORIGINS || "").split(",").map(s => s.trim()).filter(Boolean);
    const cors = corsHeaders(request.headers.get("Origin"), allowed);

    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    if (request.method !== "POST")     return json({ error: "ใช้ POST เท่านั้น" }, 405, cors);
    if (!new URL(request.url).pathname.endsWith("/analyze"))
      return json({ error: "ไม่พบปลายทางนี้" }, 404, cors);

    // กันคนอื่นมายิงจนค่า API บาน
    if (!env.APP_TOKEN || request.headers.get("X-App-Token") !== env.APP_TOKEN)
      return json({ error: "รหัสแอปไม่ถูกต้อง — ไปตั้งค่าในแอปให้ตรงกับที่ตั้งไว้ใน Worker" }, 401, cors);

    let body;
    try { body = await request.json(); }
    catch { return json({ error: "ข้อมูลที่ส่งมาไม่ใช่ JSON" }, 400, cors); }

    const image = String(body.image || "").replace(/^data:[^,]+,/, "");
    const mediaType = OK_MEDIA.includes(body.media_type) ? body.media_type : "image/jpeg";
    if (!image) return json({ error: "ไม่มีรูปมาด้วย" }, 400, cors);
    if (image.length > MAX_IMAGE_BYTES)
      return json({ error: "รูปใหญ่เกินไป ย่อรูปก่อนส่ง" }, 413, cors);

    const hint = String(body.hint || "").slice(0, 300).trim();
    const ask = hint
      ? `ดูรูปนี้แล้วประเมินพลังงานและมาโคร ผู้ใช้ใบ้มาว่า: "${hint}" — ถ้าคำใบ้ขัดกับสิ่งที่เห็นในรูป ให้เชื่อรูปเป็นหลัก แล้วเขียนบอกใน note`
      : "ดูรูปนี้แล้วประเมินพลังงานและมาโคร";

    const client = new Anthropic({ apiKey: env.ANTHROPIC_API_KEY });

    try {
      const response = await client.messages.create({
        model: env.CLAUDE_MODEL || "claude-opus-5",
        max_tokens: 2000,
        system: SYSTEM,
        messages: [{
          role: "user",
          content: [
            { type: "image", source: { type: "base64", media_type: mediaType, data: image } },
            { type: "text", text: ask }
          ]
        }],
        output_config: {
          effort: env.EFFORT || "medium",
          format: { type: "json_schema", schema: SCHEMA }
        }
      });

      if (response.stop_reason === "refusal")
        return json({ error: "Claude ไม่ตอบรูปนี้ ลองถ่ายใหม่หรือกรอกเอง" }, 422, cors);

      const text = response.content.find(b => b.type === "text")?.text;
      if (!text) return json({ error: "ไม่ได้คำตอบกลับมา" }, 502, cors);

      const data = JSON.parse(text);
      data.usage = {
        input_tokens: response.usage.input_tokens,
        output_tokens: response.usage.output_tokens
      };
      return json(data, 200, cors);

    } catch (e) {
      const status = e?.status;
      if (status === 401) return json({ error: "API key ของ Anthropic ไม่ถูกต้อง" }, 500, cors);
      if (status === 429) return json({ error: "ยิงถี่เกินไป รอสักครู่แล้วลองใหม่" }, 429, cors);
      if (status === 400) return json({ error: "คำขอไม่ถูกต้อง: " + (e.message || "") }, 400, cors);
      return json({ error: "เรียก Claude ไม่สำเร็จ: " + (e?.message || String(e)) }, 502, cors);
    }
  }
};
