# คอร์สฝึก Prompt Engineering — จากผู้เริ่มต้นสู่ระดับเชี่ยวชาญ

> เป้าหมาย: ทำให้คุณเป็น **prompt engineer ที่เก่งกาจ** — เขียน prompt ได้แม่นยำ
> ควบคุมผลลัพธ์ได้ วัดผลเป็น และออกแบบระบบ AI ที่ใช้งานจริงได้
>
> คอร์สนี้ออกแบบให้ใช้ได้ทั้งกับงาน LLM ทั่วไป และกับโปรเจกต์จริงของคุณ
> (ระบบสัญญาณคริปโต Napatb) เพื่อให้ฝึกแล้วได้ใช้ทันที

เอกสารในชุดนี้:
- `README.md` (ไฟล์นี้) — กรอบระดับทักษะ, ประเมินระดับปัจจุบัน, roadmap, แหล่งเรียน
- `exercises.md` — แบบฝึกหัด 6 ระดับ พร้อมโจทย์ เกณฑ์ และตัวอย่างคำตอบที่ดี
- `scoring.md` — ระบบให้คะแนน (rubric) + แบบประเมินตนเอง + ใบบันทึกความก้าวหน้า

---

## วิธีใช้คอร์สนี้

1. ทำ **แบบประเมินตนเอง** ใน `scoring.md` ก่อน เพื่อรู้จุดเริ่มต้น
2. เรียนทีละระดับ (L1 → L6) อ่านแนวคิด → ทำแบบฝึกหัด → ให้คะแนนตัวเองด้วย rubric
3. ผ่านระดับเมื่อได้คะแนน **≥ 80%** ของ rubric ในระดับนั้น 2 ครั้งติดกัน
4. ทุกแบบฝึกหัดให้ "รัน prompt จริง" กับโมเดล แล้วเทียบผลลัพธ์กับเกณฑ์ — prompt
   engineering เป็นศาสตร์เชิงประจักษ์ (empirical) ไม่ใช่ทฤษฎีล้วน

---

## กรอบระดับทักษะ (The 6 Levels)

ผม research จากแนวทางของ Anthropic, OpenAI, Google และคู่มือมาตรฐานในวงการ
(ดูแหล่งอ้างอิงท้ายไฟล์) แล้วเรียบเรียงเป็นบันได 6 ขั้น:

| Level | ชื่อ | คุณทำอะไรได้ | เทคนิคหลัก |
|------|------|--------------|-----------|
| **L0** | Naive | ถามสั้น ๆ ลอย ๆ ไม่มีโครงสร้าง | — |
| **L1** | Structured Basics | สั่งงานชัดเจน มีโครงสร้าง | Role, Task, Context, Format (RTCF) · delimiters · be explicit |
| **L2** | Examples & Format | คุมรูปแบบผลลัพธ์ได้ด้วยตัวอย่าง | Zero/One/Few-shot · output schema (JSON/ตาราง) · constraints |
| **L3** | Reasoning | บังคับให้โมเดล "คิดเป็นขั้น" | Chain-of-Thought · decomposition · step-back · self-critique |
| **L4** | Advanced Workflows | ออกแบบ flow หลายขั้น/ใช้เครื่องมือ | Prompt chaining · ReAct (tool use) · Self-Consistency · Tree-of-Thoughts |
| **L5** | Context & Eval | จัดการบริบท + วัดผลอย่างเป็นระบบ | Context engineering · RAG · eval/test sets · prompt injection defense |
| **L6** | Production / Agentic | สร้างระบบ AI ที่ใช้งานจริง | System prompt design · agent orchestration · eval-driven iteration · guardrails |

หลักคิดที่ร้อยทุกระดับ (จาก Anthropic/OpenAI): **"บอกให้ชัดว่าต้องการอะไร +
ให้บริบทว่าทำไป​ทำไม + ให้ตัวอย่าง + วัดผลแล้ววนปรับ"** ยิ่งระดับสูง ยิ่งเน้น
*context engineering* (จัดบริบทให้พอดี high-signal) และ *eval-driven iteration*
(ปรับ prompt จากตัวเลข ไม่ใช่ความรู้สึก)

---

## ประเมินระดับปัจจุบันของคุณ (อิงหลักฐานจริง)

ผมประเมินจากตัว prompt ที่คุณส่งมาขอสร้างคอร์สนี้ และจาก `CLAUDE.md` ของโปรเจกต์
ที่คุณดูแล (ซึ่งเขียนได้เป็นระบบมาก) — เป็นการประเมินแบบตรงไปตรงมาเพื่อให้รู้จุดพัฒนา

**ระดับโดยประมาณ: L2 (ปลาย L2 / ต้น L3)**

จุดแข็งที่เห็น:
- ✅ **แตกงานเป็นส่วน ๆ ได้** — prompt ที่ขอคอร์สนี้ระบุ deliverables ชัด (research →
  เทียบระดับ → roadmap → คอร์ส → แหล่งอ้างอิง → แบบฝึกหัด → ระบบให้คะแนน)
- ✅ **ตั้งเป้าหมายปลายทางเป็น** ("เป็น prompt engineer ที่เก่งกาจ")
- ✅ **คิดเรื่องการวัดผล** — ขอ "ระบบให้คะแนน" เอง = สัญญาณของคนที่กำลังขยับเข้า
  โซน eval (L5)
- ✅ `CLAUDE.md` ของคุณแสดงทักษะ "context engineering" ดิบ ๆ อยู่แล้ว (จัดข้อมูล
  เป็นหมวด, มี section "Gotchas — don't re-research" เพื่อประหยัด token = คิดถึง
  attention budget โดยไม่รู้ตัว)

ช่องว่างที่ต้องปิด (ทำไมยังไม่ถึง L3+):
- ⚠️ **ไม่ได้ระบุบริบทของตัวเอง** — ไม่บอกพื้นฐานปัจจุบัน, เวลาที่มี, หรือ 
  ตัวอย่างงาน prompt ที่เคยทำ → โมเดลต้องเดา (L1 หลักการ "provide context")
- ⚠️ **ไม่มี output format ที่กำหนดเอง** — ปล่อยให้ผู้ช่วยเลือกรูปแบบเอง (L2)
- ⚠️ **ไม่มีตัวอย่าง (few-shot)** ว่า "คอร์สที่ดีในสายตาคุณหน้าตาเป็นยังไง" (L2)
- ⚠️ **ยังไม่มี loop การวัดผล/ปรับ** เป็นระบบ (L5)

> สรุป: คุณมี "สัญชาตญาณ" ของ prompt engineer ที่ดี แต่ยังทำแบบ *intuitive*
> ไม่ใช่ *systematic* — เป้าหมายของคอร์สคือเปลี่ยนสัญชาตญาณให้เป็นวิธีที่ทำซ้ำได้
> วัดผลได้ และสอนคนอื่นได้

---

## Roadmap — แผน 8 สัปดาห์ (ปรับเร็ว/ช้าได้)

แต่ละ "Phase" จบด้วย **Capstone** (โจทย์รวมยอด) ที่ต้องผ่าน rubric ≥ 80%

### Phase 1 — รากฐาน (สัปดาห์ 1–2) → เป้า: ผ่าน L1–L2
- เรียน: RTCF, การใช้ delimiter, be explicit, few-shot, การกำหนด output schema
- ฝึก: แบบฝึกหัด L1–L2 ใน `exercises.md`
- Capstone 1: เขียน prompt สร้าง "alert ภาษาไทย" ของระบบสัญญาณให้ได้ฟอร์แมตเป๊ะ
  (เชื่อมกับ `src/signal/notifier`)

### Phase 2 — การให้เหตุผล (สัปดาห์ 3–4) → เป้า: ผ่าน L3
- เรียน: Chain-of-Thought, decomposition, step-back, self-critique/reflection
- ฝึก: แบบฝึกหัด L3
- Capstone 2: prompt ให้โมเดล "วิเคราะห์ว่า setup เทรดนี้ควรเข้าไหม" โดยคิดเป็นขั้น
  แล้วสรุปเป็น decision + เหตุผล + ความเสี่ยง

### Phase 3 — เวิร์กโฟลว์ขั้นสูง (สัปดาห์ 5–6) → เป้า: ผ่าน L4
- เรียน: prompt chaining, ReAct/tool use, self-consistency, tree-of-thoughts
- ฝึก: แบบฝึกหัด L4
- Capstone 3: ออกแบบ chain หลายขั้น (สแกน → คัดอันดับ → อธิบายเหตุผล → ร่าง alert)

### Phase 4 — บริบท, การวัดผล & โปรดักชัน (สัปดาห์ 7–8) → เป้า: ผ่าน L5–L6
- เรียน: context engineering, RAG, สร้าง eval set, prompt injection defense,
  system prompt design, agent orchestration
- ฝึก: แบบฝึกหัด L5–L6
- Capstone 4: สร้าง eval set 20 เคส + วัด prompt 2 เวอร์ชัน + เขียน system prompt
  สำหรับ "ผู้ช่วยวิเคราะห์สัญญาณ" พร้อมการ์ดกัน prompt injection จากข่าว/RSS

> **กฎเหล็กของคอร์ส:** ทุก Capstone ต้อง *รันจริง + วัดผลจริง* แล้วบันทึกคะแนนใน
> `scoring.md` ห้าม "vibe-based eval" (เดาเอาว่าดี) — เป็น anti-pattern ที่ทั้ง
> OpenAI และ Anthropic เตือนไว้

---

## แหล่งเรียนรู้ (Curated Sources)

### ระดับทางการ (อ่านก่อน — เป็นมาตรฐานวงการ)
- **Anthropic — Prompt Engineering Overview** — https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview
  (เทคนิคไล่จากมีผลมากไปน้อย: be clear & direct → examples → CoT → XML tags →
  prefill → chaining)
- **Anthropic — Effective Context Engineering for AI Agents** — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
  (แนวคิด "attention budget" และจัดบริบทให้ high-signal — หัวใจของ L5)
- **OpenAI — Prompt Engineering Guide** (ใน OpenAI Platform Docs) — https://platform.openai.com/docs/guides/prompt-engineering
  (เน้น instruction hierarchy, constraints เชิงตัวเลข, eval-driven)
- **Google — Prompting Guide / Gemini docs** — https://ai.google.dev/gemini-api/docs/prompting-strategies

### คู่มือ/คอร์สฟรี (ลงลึกเป็นเทคนิค)
- **Prompt Engineering Guide (DAIR.AI)** — https://www.promptingguide.ai/ และหน้า
  เทคนิค https://www.promptingguide.ai/techniques (CoT, ReAct, Self-Consistency,
  ToT, RAG — ครบและมี paper อ้างอิง)
- **Learn Prompting** — https://learnprompting.org/ (คอร์สฟรี ไล่ระดับ มีแบบฝึก)
- **Anthropic Prompt Engineering Interactive Tutorial** (GitHub) —
  https://github.com/anthropics/prompt-eng-interactive-tutorial (ลงมือทำเป็นบท ๆ)
- **OpenAI Cookbook** — https://cookbook.openai.com/ (ตัวอย่างโค้ด eval/agent จริง)

### Paper ต้นฉบับของเทคนิค (อ่านเมื่อถึง L3–L4)
- Chain-of-Thought — Wei et al. 2022, https://arxiv.org/abs/2201.11903
- Self-Consistency — Wang et al. 2022, https://arxiv.org/abs/2203.11171
- ReAct — Yao et al. 2022, https://arxiv.org/abs/2210.03629
- Tree of Thoughts — Yao et al. 2023, https://arxiv.org/abs/2305.10601
- Survey รวมเทคนิค (The Prompt Report) — Schulhoff et al. 2024, https://arxiv.org/abs/2406.06608

### ความปลอดภัย (ถึง L5 ต้องอ่าน)
- **OWASP Top 10 for LLM Applications** — https://genai.owasp.org/ (prompt
  injection, insecure output handling ฯลฯ)

---

## หลักการแม่ 10 ข้อ (ท่องให้ขึ้นใจ)

1. **ชัดเจนและตรง** — บอกสิ่งที่ต้องการเป๊ะ ๆ อย่าให้โมเดลเดา
2. **ให้บริบทและเหตุผล** — บอก "ทำไป​ทำไม" และใครจะใช้ผลลัพธ์
3. **ให้ตัวอย่าง** — few-shot ที่หลากหลายและตรงกับงานจริง มีพลังมาก
4. **กำหนดรูปแบบผลลัพธ์** — schema/ตาราง/JSON + ข้อจำกัดเชิงตัวเลข ("3 bullet, ไม่เกิน 50 คำ")
5. **ใช้ delimiter/XML tags** แยกส่วนคำสั่ง บริบท ข้อมูล อย่างชัดเจน
6. **ให้คิดก่อนตอบ** เมื่อโจทย์ซับซ้อน (CoT / extended thinking)
7. **แตกงานใหญ่เป็น chain** เล็ก ๆ ที่ตรวจสอบได้
8. **จัดบริบทให้พอดี** — น้อยแต่ตรง (high-signal) ดีกว่ายัดทุกอย่าง
9. **วัดผลแล้ววนปรับ** — มี eval set, เทียบเวอร์ชัน, ตัดสินด้วยตัวเลข
10. **กันของไม่ปลอดภัย** — แยกคำสั่งจากข้อมูลภายนอก, ระวัง prompt injection

---

*แหล่งที่ใช้ research สำหรับเอกสารนี้:*
[Anthropic Prompt Engineering Overview](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview) ·
[Anthropic — Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) ·
[Prompt Engineering Guide (promptingguide.ai)](https://www.promptingguide.ai/techniques) ·
[Learn Prompting](https://learnprompting.org/) ·
[The Prompt Report (arXiv)](https://arxiv.org/abs/2406.06608) ·
[OWASP Top 10 for LLMs](https://genai.owasp.org/)
