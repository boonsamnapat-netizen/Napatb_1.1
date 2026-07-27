"""TCAS70 — ระบบเตรียมสอบแพทย์ (กสพท).

โมดูลนี้แยกขาดจากระบบ crypto signal ใน src/signal/ อย่างสิ้นเชิง
ใช้ร่วมกันแค่ธรรมเนียมการเขียนโค้ด (config YAML + CLI + Telegram notifier)

ส่วนประกอบ
  syllabus  — โครงสร้างวิชา/หัวข้อ TCAS70 พร้อมน้ำหนักการออกสอบ
  planner   — สร้างตารางอ่านหนังสือรายวัน + คิวทบทวน
  quiz      — คลังข้อสอบ + รันชุดข้อสอบ + เก็บสถิติ
  srs       — spaced repetition (SM-2 แบบย่อ)
  scoring   — คำนวณคะแนนรวม กสพท + เช็คเกณฑ์ขั้นต่ำ
  ranking   — จัดอันดับคณะและประเมินโอกาส
  store     — เก็บความคืบหน้าลง JSON
  notifier  — ส่ง Telegram
  report    — เรนเดอร์ข้อความภาษาไทย
"""

__all__ = [
    "config",
    "models",
    "syllabus",
    "planner",
    "quiz",
    "srs",
    "scoring",
    "ranking",
    "store",
    "notifier",
    "report",
]
