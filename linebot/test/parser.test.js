import test from "node:test";
import assert from "node:assert/strict";

import { parseMessage } from "../src/parser/index.js";
import { thaiDigitsToArabic, findArabicNumbers, findThaiWordNumber } from "../src/lib/numbers.js";
import { localDate, bangkokIso, looksLikeSchedule, formatThaiDate } from "../src/lib/thaidate.js";

// A fixed instant so every date assertion is deterministic:
// 2026-08-23 10:00 Bangkok (= 03:00 UTC), a Sunday.
const NOW = new Date("2026-08-23T03:00:00Z");

/** Parse and assert we got exactly one entry back. */
async function single(text, recall) {
  const result = await parseMessage(text, NOW, recall);
  assert.equal(result.kind, "entries", `expected entries for ${text}, got ${result.kind}`);
  assert.equal(result.entries.length, 1, `expected 1 entry for ${text}`);
  return result.entries[0];
}

test("Thai digits convert to Arabic", () => {
  assert.equal(thaiDigitsToArabic("๕๐๐"), "500");
  assert.equal(thaiDigitsToArabic("ข้าว ๑๒๐ บาท"), "ข้าว 120 บาท");
});

test("numbers: separators, decimals and scale suffixes", () => {
  const value = (t) => findArabicNumbers(t)[0].value;
  assert.equal(value("1,200"), 1200);
  assert.equal(value("1.2k"), 1200);
  assert.equal(value("2หมื่น"), 20000);
  assert.equal(value("1.5พัน"), 1500);
  assert.equal(value("85บาท"), 85);
  assert.equal(value("99.50"), 99.5);
});

test("spelled-out numerals need two tokens, so common words are not numbers", () => {
  assert.equal(findThaiWordNumber("หนึ่งพัน").value, 1000);
  assert.equal(findThaiWordNumber("ยี่สิบห้า").value, 25);
  assert.equal(findThaiWordNumber("สองร้อยห้าสิบ").value, 250);
  assert.equal(findThaiWordNumber("สิบเอ็ด").value, 11);
  assert.equal(findThaiWordNumber("สามหมื่น").value, 30000);
  // Single tokens are rejected on purpose — these are ordinary words.
  assert.equal(findThaiWordNumber("แสนแพง"), null);
  assert.equal(findThaiWordNumber("สี่แยก"), null);
});

// ---- money ------------------------------------------------------------------

test("expense: the shortest form works", async () => {
  const entry = await single("ข้าวเช้า 50");
  assert.equal(entry.type, "expense");
  assert.equal(entry.amount, 50);
  assert.equal(entry.label, "ข้าวเช้า");
  assert.equal(entry.needsConfirm, true, "no unit and no verb — should invite a correction");
});

test("expense: a unit removes the ambiguity", async () => {
  const entry = await single("กาแฟ 120 บาท");
  assert.equal(entry.type, "expense");
  assert.equal(entry.amount, 120);
  assert.equal(entry.label, "กาแฟ");
  assert.equal(entry.needsConfirm, false);
  assert.equal(entry.category, "food");
});

test("expense: a verb removes the ambiguity too", async () => {
  const entry = await single("จ่ายค่าไฟ 1,200");
  assert.equal(entry.type, "expense");
  assert.equal(entry.amount, 1200);
  assert.equal(entry.label, "ค่าไฟ");
  assert.equal(entry.category, "utilities");
});

test("income: keyword", async () => {
  const entry = await single("ได้เงินเดือน 30000");
  assert.equal(entry.type, "income");
  assert.equal(entry.amount, 30000);
  assert.equal(entry.category, "salary");
});

test("income: explicit plus sign overrides everything", async () => {
  const entry = await single("+30000 โบนัส");
  assert.equal(entry.type, "income");
  assert.equal(entry.amount, 30000);
  assert.equal(entry.label, "โบนัส");
});

test("expense: explicit minus sign", async () => {
  const entry = await single("-250 ข้าวเย็น");
  assert.equal(entry.type, "expense");
  assert.equal(entry.amount, 250);
});

test("the unit-bearing number wins over other numbers in the line", async () => {
  const entry = await single("ซื้อกาแฟ 2 แก้ว 120 บาท");
  assert.equal(entry.amount, 120);
});

test("with no unit anywhere, the last number is the amount", async () => {
  // "7-11" must not be mistaken for the price.
  const entry = await single("ซื้อของ 7-11 250");
  assert.equal(entry.amount, 250);
});

test("past day words move the date back", async () => {
  const entry = await single("เมื่อวานกินหมูกระทะ 350 บาท");
  assert.equal(entry.localDate, "2026-08-22");
  assert.equal(entry.amount, 350);

  const before = await single("เมื่อวานซืนจ่ายค่าน้ำ 300 บาท");
  assert.equal(before.localDate, "2026-08-21");
  const todayEntry = await single("วันนี้ซื้อขนม 40 บาท");
  assert.equal(todayEntry.localDate, "2026-08-23");
});

test("stored timestamps carry the Bangkok offset", async () => {
  const entry = await single("ข้าว 50 บาท");
  assert.equal(entry.occurredAt, "2026-08-23T10:00:00+07:00");
});

test("two priced items in one message become two entries", async () => {
  const result = await parseMessage("จ่ายค่าไฟ 1200 บาท กับค่าน้ำ 300 บาท", NOW);
  assert.equal(result.entries.length, 2);
  assert.equal(result.entries[0].amount, 1200);
  assert.equal(result.entries[1].amount, 300);
  assert.equal(result.entries[1].label, "ค่าน้ำ");
});

test("a single item whose name contains กับ is not split", async () => {
  const entry = await single("ข้าวกับหมู 60 บาท");
  assert.equal(entry.amount, 60);
});

// ---- calories ---------------------------------------------------------------

test("calorie: an explicit unit routes the message", async () => {
  const entry = await single("ข้าวมันไก่ 600 แคล");
  assert.equal(entry.type, "calorie");
  assert.equal(entry.direction, "intake");
  assert.equal(entry.kcal, 600);
  assert.equal(entry.label, "ข้าวมันไก่");
});

test("calorie: the ค prefix forces the reading of an otherwise ambiguous line", async () => {
  const entry = await single("ค ข้าวมันไก่ 600");
  assert.equal(entry.type, "calorie");
  assert.equal(entry.kcal, 600);
  assert.equal(entry.label, "ข้าวมันไก่");

  // Without it the same text is money — that is the whole point of the prefix.
  const asMoney = await single("ข้าวมันไก่ 600");
  assert.equal(asMoney.type, "expense");
});

test("the บ prefix forces money for a dish the bot has memorised", async () => {
  const entry = await single("บ ข้าวมันไก่ 60");
  assert.equal(entry.type, "expense");
  assert.equal(entry.amount, 60);
});

test("calorie: exercise counts as burn, and minutes are not calories", async () => {
  const entry = await single("วิ่ง 30 นาที 300 แคล");
  assert.equal(entry.type, "calorie");
  assert.equal(entry.direction, "burn");
  assert.equal(entry.kcal, 300, "300 kcal, not 30 — the duration must not be read as the figure");
  assert.equal(entry.durationMin, 30);
});

test("calorie: hours become minutes", async () => {
  const entry = await single("ว่ายน้ำ 1 ชั่วโมง 400 แคล");
  assert.equal(entry.durationMin, 60);
  assert.equal(entry.kcal, 400);
});

test("calorie: an unknown dish is asked about, never guessed", async () => {
  const result = await parseMessage("ค ส้มตำ", NOW);
  assert.equal(result.kind, "need_figure");
  assert.equal(result.label, "ส้มตำ");
});

test("calorie: a remembered dish needs no number", async () => {
  const recall = async (name) => (name === "ข้าวมันไก่" ? { kcal: 600, direction: "intake" } : null);
  const entry = await single("ค ข้าวมันไก่", recall);
  assert.equal(entry.kcal, 600);
  assert.equal(entry.fromMemory, true);
});

test("a message naming both units records money and calories", async () => {
  const result = await parseMessage("หมูกระทะ 800 แคล จ่าย 350 บาท", NOW);
  assert.equal(result.entries.length, 2);
  const money = result.entries.find((e) => e.type === "expense");
  const calorie = result.entries.find((e) => e.type === "calorie");
  assert.equal(money.amount, 350);
  assert.equal(calorie.kcal, 800);
});

test("a money unit outranks an exercise word", async () => {
  // "เดินไปซื้อของ 50 บาท" is shopping, not cardio.
  const entry = await single("เดินไปซื้อของ 50 บาท");
  assert.equal(entry.type, "expense");
  assert.equal(entry.amount, 50);
});

// ---- guards -----------------------------------------------------------------

test("schedule messages are refused, not filed as expenses", async () => {
  for (const text of [
    "พรุ่งนี้ 2 ทุ่ม โทรหาแม่",
    "8 โมง อ่านหนังสือ",
    "เตือนทุกวัน 7 โมงเช้า กินยา",
    "จันทร์หน้าไปหาหมอ",
    "บ่าย 3 ประชุม",
    "เตือนวันที่ 5 จ่ายบัตรเครดิต 4500",
    "20:30 ดูหนัง",
  ]) {
    const result = await parseMessage(text, NOW);
    assert.equal(result.kind, "unsupported", `${text} should be refused`);
    assert.equal(result.feature, "task", `${text} should be flagged as a task`);
  }
});

test("ชั่วโมง does not read as a clock time", () => {
  assert.equal(looksLikeSchedule("วิ่ง 2 ชั่วโมง"), false);
  assert.equal(looksLikeSchedule("8 โมง ประชุม"), true);
});

test("a time word glued to another Thai word is part of that word", async () => {
  // Thai has no spaces, so เที่ยง sits inside ข้าวเที่ยง and มื้อเที่ยง. Lunch
  // must stay an expense rather than becoming a noon reminder.
  assert.equal(looksLikeSchedule("ข้าวเที่ยง 80 บาท"), false);
  assert.equal(looksLikeSchedule("มื้อเที่ยง 120"), false);
  assert.equal(looksLikeSchedule("ข้าวเย็นนี้ 90 บาท"), false);
  // Standing on its own it is still a time.
  assert.equal(looksLikeSchedule("เที่ยงประชุม"), true);
  assert.equal(looksLikeSchedule("พรุ่งนี้เที่ยงกินข้าว"), true);

  const lunch = await single("ข้าวเที่ยง 80 บาท");
  assert.equal(lunch.amount, 80);
  const meal = await single("มื้อเที่ยง 120 บาท");
  assert.equal(meal.type, "expense");
});

// ---- commands ---------------------------------------------------------------

test("commands", async () => {
  const cmd = (text) => parseMessage(text, NOW);
  assert.equal((await cmd("สรุป")).name, "summary_day");
  assert.equal((await cmd("สรุปเดือน")).name, "summary_month");
  assert.equal((await cmd("ลบ")).index, 1);
  assert.equal((await cmd("ลบ 3")).index, 3);
  assert.equal((await cmd("แก้ 1500")).amount, 1500);
  assert.equal((await cmd("help")).name, "help");
});

test("calorie commands", async () => {
  const cmd = (text) => parseMessage(text, NOW);

  const remember = await cmd("จำ ข้าวมันไก่ 600");
  assert.equal(remember.name, "remember");
  assert.equal(remember.label, "ข้าวมันไก่");
  assert.equal(remember.kcal, 600);

  assert.equal((await cmd("ลืม ข้าวมันไก่")).label, "ข้าวมันไก่");
  assert.equal((await cmd("รายการจำ")).name, "memories");
  assert.equal((await cmd("เป้า 2000")).kcal, 2000);
  assert.equal((await cmd("เป้า")).kcal, null, "bare เป้า asks rather than sets");
});

test("messages with no amount are reported as unparsed", async () => {
  assert.equal((await parseMessage("สวัสดี", NOW)).kind, "unparsed");
  assert.equal((await parseMessage("", NOW)).kind, "unparsed");
});

test("date helpers", () => {
  assert.equal(localDate(NOW), "2026-08-23");
  assert.equal(localDate(NOW, -1), "2026-08-22");
  assert.equal(formatThaiDate("2026-08-23"), "23 ส.ค.");
  // 22:00 UTC is already the next day in Bangkok.
  assert.equal(localDate(new Date("2026-08-23T22:00:00Z")), "2026-08-24");
  assert.equal(bangkokIso(new Date("2026-08-23T22:00:00Z")), "2026-08-24T05:00:00+07:00");
});
