"""โครงสร้างวิชา/หัวข้อสำหรับสายแพทย์ กสพท (TCAS70).

น้ำหนัก (weight 1-5) = ความถี่/ปริมาณข้อที่ออกสอบโดยประมาณ อิงจากรูปแบบข้อสอบ
A-Level และ TPAT1 ที่ผ่านมา — ปรับได้ตามข้อสอบจริงที่เจอ
hours = ชั่วโมงที่ควรใช้อ่านรอบแรกให้เข้าใจ + ทำโจทย์พอสมควร

รวมทุกวิชาประมาณ 600+ ชั่วโมง ซึ่งตรงกับที่เด็กเตรียมแพทย์ใช้จริงในหนึ่งปี
"""

from __future__ import annotations

from typing import Dict, List

from .models import Subject, Topic


def _t(code: str, name: str, weight: int, hours: float) -> Topic:
    return Topic(code=code, name=name, weight=weight, hours=hours)


# --------------------------------------------------------------- TPAT1 กสพท
TPAT1 = Subject(
    code="tpat1",
    short="TPAT1",
    name="TPAT1 วิชาเฉพาะ กสพท",
    exam="tpat1",
    group="tpat1",
    max_score=300.0,
    topics=[
        _t("tpat1_series", "เชาวน์: อนุกรมตัวเลข/ตัวอักษร", 5, 8),
        _t("tpat1_analogy", "เชาวน์: อุปมาอุปไมย", 4, 6),
        _t("tpat1_spatial", "เชาวน์: มิติสัมพันธ์/ภาพพับ-ภาพหมุน", 5, 10),
        _t("tpat1_logic", "เชาวน์: ตรรกะและเงื่อนไข", 5, 10),
        _t("tpat1_quant", "เชาวน์: คณิตคิดเร็ว/ตีความข้อมูล", 4, 8),
        _t("tpat1_ethics_principle", "จริยธรรม: หลักจริยธรรมทางการแพทย์ 4 ข้อ", 5, 6),
        _t("tpat1_ethics_case", "จริยธรรม: วิเคราะห์สถานการณ์/เลือกการกระทำ", 5, 14),
        _t("tpat1_ethics_prof", "จริยธรรม: จรรยาบรรณวิชาชีพและกฎหมายที่เกี่ยวข้อง", 3, 6),
        _t("tpat1_connect_basic", "เชื่อมโยง: หลักการทำและสัญลักษณ์ A D F H", 5, 6),
        _t("tpat1_connect_drill", "เชื่อมโยง: ฝึกทำบทความจับเวลา", 5, 20),
    ],
)

# ------------------------------------------------------------------ ชีววิทยา
BIO = Subject(
    code="bio",
    short="ชีววิทยา",
    name="A-Level ชีววิทยา",
    exam="alevel",
    group="science",
    max_score=100.0,
    topics=[
        _t("bio_chem", "เคมีพื้นฐานของสิ่งมีชีวิต", 2, 4),
        _t("bio_cell", "เซลล์และการลำเลียงสารผ่านเยื่อ", 4, 7),
        _t("bio_resp", "การหายใจระดับเซลล์", 4, 6),
        _t("bio_photo", "การสังเคราะห์ด้วยแสง", 4, 7),
        _t("bio_division", "การแบ่งเซลล์ (ไมโทซิส/ไมโอซิส)", 4, 5),
        _t("bio_mendel", "พันธุศาสตร์เมนเดลและการถ่ายทอดลักษณะ", 5, 9),
        _t("bio_molgen", "พันธุศาสตร์โมเลกุล DNA/RNA/การสังเคราะห์โปรตีน", 5, 9),
        _t("bio_biotech", "เทคโนโลยีทาง DNA", 3, 4),
        _t("bio_evolution", "วิวัฒนาการและพันธุศาสตร์ประชากร", 4, 6),
        _t("bio_diversity", "ความหลากหลายทางชีวภาพและอนุกรมวิธาน", 3, 6),
        _t("bio_plant_struct", "โครงสร้างและหน้าที่ของพืช", 4, 7),
        _t("bio_plant_repro", "การสืบพันธุ์และการตอบสนองของพืช", 3, 5),
        _t("bio_digest", "ระบบย่อยอาหารและการสลายสารอาหาร", 4, 5),
        _t("bio_circ", "ระบบหมุนเวียนเลือดและน้ำเหลือง", 5, 7),
        _t("bio_immune", "ระบบภูมิคุ้มกัน", 4, 5),
        _t("bio_breath", "ระบบหายใจและการแลกเปลี่ยนแก๊ส", 4, 5),
        _t("bio_excrete", "ระบบขับถ่ายและการรักษาดุลยภาพ", 4, 6),
        _t("bio_nerve", "ระบบประสาทและอวัยวะรับความรู้สึก", 5, 9),
        _t("bio_endocrine", "ระบบต่อมไร้ท่อและฮอร์โมน", 5, 7),
        _t("bio_repro", "ระบบสืบพันธุ์และการเจริญเติบโตของสัตว์", 4, 6),
        _t("bio_behavior", "พฤติกรรมของสัตว์", 2, 3),
        _t("bio_ecology", "ระบบนิเวศ ประชากร และมนุษย์กับสิ่งแวดล้อม", 3, 6),
    ],
)

# ---------------------------------------------------------------------- เคมี
CHEM = Subject(
    code="chem",
    short="เคมี",
    name="A-Level เคมี",
    exam="alevel",
    group="science",
    max_score=100.0,
    topics=[
        _t("chem_atom", "อะตอมและสมบัติของธาตุ/ตารางธาตุ", 4, 7),
        _t("chem_bond", "พันธะเคมีและรูปร่างโมเลกุล", 5, 9),
        _t("chem_mole", "ปริมาณสัมพันธ์ (โมล สมการเคมี สารละลาย)", 5, 12),
        _t("chem_gas", "แก๊สและสมบัติของแก๊ส", 3, 5),
        _t("chem_rate", "อัตราการเกิดปฏิกิริยาเคมี", 4, 7),
        _t("chem_equilibrium", "สมดุลเคมี", 5, 9),
        _t("chem_acidbase", "กรด-เบส และการไทเทรต", 5, 11),
        _t("chem_redox", "ไฟฟ้าเคมี (รีดอกซ์ เซลล์กัลวานิก/อิเล็กโทรลิติก)", 5, 10),
        _t("chem_organic", "เคมีอินทรีย์ (หมู่ฟังก์ชัน ปฏิกิริยา ไอโซเมอร์)", 5, 12),
        _t("chem_polymer", "พอลิเมอร์", 2, 3),
        _t("chem_biomol", "สารชีวโมเลกุล", 3, 5),
        _t("chem_industry", "ธาตุและสารประกอบในอุตสาหกรรม/เชื้อเพลิง", 2, 4),
        _t("chem_lab", "ทักษะปฏิบัติการและความปลอดภัย", 2, 3),
    ],
)

# -------------------------------------------------------------------- ฟิสิกส์
PHYS = Subject(
    code="phys",
    short="ฟิสิกส์",
    name="A-Level ฟิสิกส์",
    exam="alevel",
    group="science",
    max_score=100.0,
    topics=[
        _t("phys_kinematics", "การเคลื่อนที่แนวตรงและการเคลื่อนที่แบบโพรเจกไทล์", 5, 9),
        _t("phys_newton", "แรงและกฎการเคลื่อนที่ของนิวตัน", 5, 9),
        _t("phys_equilibrium", "สมดุลกลและโมเมนต์", 3, 5),
        _t("phys_work", "งาน พลังงาน และกำลัง", 4, 7),
        _t("phys_momentum", "โมเมนตัมและการชน", 4, 6),
        _t("phys_circular", "การเคลื่อนที่แบบวงกลมและการหมุน", 4, 7),
        _t("phys_shm", "การเคลื่อนที่แบบฮาร์มอนิกอย่างง่าย", 3, 5),
        _t("phys_wave", "คลื่นกลและสมบัติของคลื่น", 4, 7),
        _t("phys_sound", "เสียงและการได้ยิน", 3, 5),
        _t("phys_light", "แสงและทัศนอุปกรณ์", 4, 7),
        _t("phys_heat", "ความร้อน แก๊ส และทฤษฎีจลน์", 3, 6),
        _t("phys_fluid", "ของไหล", 3, 5),
        _t("phys_estatic", "ไฟฟ้าสถิต", 4, 7),
        _t("phys_ecurrent", "ไฟฟ้ากระแสและวงจร", 5, 9),
        _t("phys_magnet", "แม่เหล็กไฟฟ้าและไฟฟ้ากระแสสลับ", 4, 8),
        _t("phys_modern", "ฟิสิกส์อะตอม นิวเคลียร์ และควอนตัม", 3, 6),
    ],
)

# ---------------------------------------------------------- คณิตศาสตร์ประยุกต์ 1
MATH = Subject(
    code="math1",
    short="คณิต 1",
    name="A-Level คณิตศาสตร์ประยุกต์ 1",
    exam="alevel",
    group="math1",
    max_score=100.0,
    topics=[
        _t("math_set_logic", "เซตและตรรกศาสตร์", 3, 5),
        _t("math_real", "จำนวนจริง สมการ อสมการ ค่าสัมบูรณ์", 4, 7),
        _t("math_function", "ความสัมพันธ์และฟังก์ชัน", 5, 9),
        _t("math_explog", "ฟังก์ชันเอกซ์โพเนนเชียลและลอการิทึม", 5, 8),
        _t("math_trig", "ตรีโกณมิติและการประยุกต์", 5, 10),
        _t("math_matrix", "เมทริกซ์และดีเทอร์มิแนนต์", 4, 6),
        _t("math_vector", "เวกเตอร์ในสามมิติ", 4, 6),
        _t("math_complex", "จำนวนเชิงซ้อน", 4, 6),
        _t("math_sequence", "ลำดับและอนุกรม", 5, 8),
        _t("math_calculus", "แคลคูลัส: ลิมิต อนุพันธ์ อินทิกรัล", 5, 14),
        _t("math_prob", "การเรียงสับเปลี่ยน การจัดหมู่ และความน่าจะเป็น", 5, 10),
        _t("math_stat", "สถิติ การกระจาย และการแจกแจงปกติ", 4, 8),
    ],
)

# ------------------------------------------------------------------- อังกฤษ
ENG = Subject(
    code="eng",
    short="อังกฤษ",
    name="A-Level ภาษาอังกฤษ",
    exam="alevel",
    group="english",
    max_score=100.0,
    topics=[
        _t("eng_reading", "Reading comprehension (บทความยาว)", 5, 18),
        _t("eng_vocab", "Vocabulary in context / คำศัพท์ทางการแพทย์-วิทยาศาสตร์", 5, 14),
        _t("eng_cloze", "Cloze test", 4, 8),
        _t("eng_grammar", "Grammar & structure", 4, 10),
        _t("eng_error", "Error identification", 3, 6),
        _t("eng_conversation", "Conversation / situational dialogue", 4, 7),
        _t("eng_organization", "Paragraph organization & writing", 3, 6),
    ],
)

# ---------------------------------------------------------------------- ไทย
THAI = Subject(
    code="thai",
    short="ไทย",
    name="A-Level ภาษาไทย",
    exam="alevel",
    group="thai",
    max_score=100.0,
    topics=[
        _t("thai_reading", "การอ่านจับใจความ ตีความ และสรุปความ", 5, 8),
        _t("thai_reason", "การใช้เหตุผลและการอนุมาน", 4, 5),
        _t("thai_grammar", "หลักภาษา: คำ ชนิดของคำ ประโยค", 4, 6),
        _t("thai_usage", "การใช้ภาษาให้ถูกต้องและเหมาะสมกับระดับภาษา", 4, 5),
        _t("thai_rhetoric", "โวหารและภาพพจน์", 3, 3),
        _t("thai_literature", "วรรณคดีและวรรณกรรม", 3, 5),
        _t("thai_writing", "การเขียนสื่อสารและเรียงลำดับข้อความ", 3, 4),
    ],
)

# -------------------------------------------------------------------- สังคม
SOCIAL = Subject(
    code="social",
    short="สังคม",
    name="A-Level สังคมศึกษา",
    exam="alevel",
    group="social",
    max_score=100.0,
    topics=[
        _t("soc_religion", "ศาสนา ศีลธรรม จริยธรรม", 4, 6),
        _t("soc_civic", "หน้าที่พลเมือง วัฒนธรรม และการเมืองการปกครอง", 4, 6),
        _t("soc_law", "กฎหมายที่ควรรู้", 3, 4),
        _t("soc_econ", "เศรษฐศาสตร์", 4, 6),
        _t("soc_history_th", "ประวัติศาสตร์ไทย", 3, 5),
        _t("soc_history_world", "ประวัติศาสตร์สากล", 3, 5),
        _t("soc_geo", "ภูมิศาสตร์และสิ่งแวดล้อม", 4, 6),
    ],
)


SUBJECTS: Dict[str, Subject] = {
    s.code: s for s in [TPAT1, BIO, CHEM, PHYS, MATH, ENG, THAI, SOCIAL]
}

# กลุ่มถ่วงน้ำหนัก -> วิชาที่อยู่ในกลุ่ม (ใช้ตอนคำนวณคะแนน กสพท)
GROUPS: Dict[str, List[str]] = {}
for _code, _subj in SUBJECTS.items():
    GROUPS.setdefault(_subj.group, []).append(_code)


def get_subject(code: str) -> Subject:
    if code not in SUBJECTS:
        raise KeyError(
            f"ไม่รู้จักวิชา '{code}' — วิชาที่มี: {', '.join(sorted(SUBJECTS))}"
        )
    return SUBJECTS[code]


def get_topic(subject_code: str, topic_code: str) -> Topic:
    for t in get_subject(subject_code).topics:
        if t.code == topic_code:
            return t
    raise KeyError(f"ไม่รู้จักหัวข้อ '{topic_code}' ในวิชา '{subject_code}'")


def find_topic(topic_code: str):
    """หาหัวข้อจากรหัสอย่างเดียว คืน (subject, topic) หรือ (None, None)."""
    for subj in SUBJECTS.values():
        for t in subj.topics:
            if t.code == topic_code:
                return subj, t
    return None, None


def all_topics() -> List[tuple]:
    """คืน [(subject, topic), ...] ทุกหัวข้อในทุกวิชา."""
    return [(s, t) for s in SUBJECTS.values() for t in s.topics]


def total_hours() -> float:
    return sum(s.total_hours for s in SUBJECTS.values())
