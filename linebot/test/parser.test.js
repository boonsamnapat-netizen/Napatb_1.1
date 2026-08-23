import test from "node:test";
import assert from "node:assert/strict";

import { parseMessage } from "../src/parser/index.js";
import { thaiDigitsToArabic, findArabicNumbers, findThaiWordNumber } from "../src/lib/numbers.js";
import { localDate, bangkokIso, looksLikeSchedule, formatThaiDate } from "../src/lib/thaidate.js";

// A fixed instant so every date assertion is deterministic:
// 2026-08-23 10:00 Bangkok (= 03:00 UTC), a Sunday.
const NOW = new Date("2026-08-23T03:00:00Z");

/** Parse and assert we got exactly one entry back. */
function single(text) {
  const result = parseMessage(text, NOW);
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

test("expense: the shortest form works", () => {
  const entry = single("ข้าวเช้า 50");
  assert.equal(entry.type, "expense");
  assert.equal(entry.amount, 50);
  assert.equal(entry.label, "ข้าวเช้า");
  assert.equal(entry.needsConfirm, true, "no unit and no verb — should invite a correction");
});

test("expense: a unit removes the ambiguity", () => {
  const entry = single("กาแฟ 120 บาท");
  assert.equal(entry.type, "expense");
  assert.equal(entry.amount, 120);
  assert.equal(entry.label, "กาแฟ");
  assert.equal(entry.needsConfirm, false);
  assert.equal(entry.category, "food");
});

test("expense: a verb removes the ambiguity too", () => {
  const entry = single("จ่ายค่าไฟ 1,200");
  assert.equal(entry.type, "expense");
  assert.equal(entry.amount, 1200);
  assert.equal(entry.label, "ค่าไฟ");
  assert.equal(entry.category, "utilities");
  assert.equal(entry.needsConfirm, false);
});

test("income: keyword", () => {
  const entry = single("ได้เงินเดือน 30000");
  assert.equal(entry.type, "income");
  assert.equal(entry.amount, 30000);
  assert.equal(entry.category, "salary");
});

test("income: explicit plus sign overrides everything", () => {
  const entry = single("+30000 โบนัส");
  assert.equal(entry.type, "income");
  assert.equal(entry.amount, 30000);
  assert.equal(entry.label, "โบนัส");
});

test("expense: explicit minus sign", () => {
  const entry = single("-250 ข้าวเย็น");
  assert.equal(entry.type, "expense");
  assert.equal(entry.amount, 250);
});

test("the unit-bearing number wins over other numbers in the line", () => {
  const entry = single("ซื้อกาแฟ 2 แก้ว 120 บาท");
  assert.equal(entry.amount, 120);
});

test("with no unit anywhere, the last number is the amount", () => {
  // "7-11" must not be mistaken for the price.
  const entry = single("ซื้อของ 7-11 250");
  assert.equal(entry.amount, 250);
});

test("past day words move the date back", () => {
  const entry = single("เมื่อวานกินหมูกระทะ 350 บาท");
  assert.equal(entry.localDate, "2026-08-22");
  assert.equal(entry.amount, 350);
  assert.equal(entry.label, "กินหมูกระทะ");

  assert.equal(single("เมื่อวานซืนจ่ายค่าน้ำ 300 บาท").localDate, "2026-08-21");
  assert.equal(single("วันนี้ซื้อขนม 40 บาท").localDate, "2026-08-23");
});

test("stored timestamps carry the Bangkok offset", () => {
  const entry = single("ข้าว 50 บาท");
  assert.equal(entry.occurredAt, "2026-08-23T10:00:00+07:00");
  assert.match(entry.occurredAt, /\+07:00$/);
});

test("two priced items in one message become two entries", () => {
  const result = parseMessage("จ่ายค่าไฟ 1200 บาท กับค่าน้ำ 300 บาท", NOW);
  assert.equal(result.kind, "entries");
  assert.equal(result.entries.length, 2);
  assert.equal(result.entries[0].amount, 1200);
  assert.equal(result.entries[1].amount, 300);
  assert.equal(result.entries[1].label, "ค่าน้ำ");
});

test("a single item whose name contains กับ is not split", () => {
  const entry = single("ข้าวกับหมู 60 บาท");
  assert.equal(entry.amount, 60);
});

test("schedule messages are refused, not filed as expenses", () => {
  for (const text of [
    "พรุ่งนี้ 2 ทุ่ม โทรหาแม่",
    "8 โมง อ่านหนังสือ",
    "เตือนทุกวัน 7 โมงเช้า กินยา",
    "จันทร์หน้าไปหาหมอ",
    "บ่าย 3 ประชุม",
    "เตือนวันที่ 5 จ่ายบัตรเครดิต 4500",
    "20:30 ดูหนัง",
  ]) {
    const result = parseMessage(text, NOW);
    assert.equal(result.kind, "unsupported", `${text} should be refused`);
    assert.equal(result.feature, "task", `${text} should be flagged as a task`);
  }
});

test("ชั่วโมง does not read as a clock time", () => {
  assert.equal(looksLikeSchedule("วิ่ง 2 ชั่วโมง"), false);
  assert.equal(looksLikeSchedule("8 โมง ประชุม"), true);
});

test("a time word glued to another Thai word is part of that word", () => {
  // Thai has no spaces, so เที่ยง sits inside ข้าวเที่ยง and มื้อเที่ยง. Lunch
  // must stay an expense rather than becoming a noon reminder.
  assert.equal(looksLikeSchedule("ข้าวเที่ยง 80 บาท"), false);
  assert.equal(looksLikeSchedule("มื้อเที่ยง 120"), false);
  assert.equal(looksLikeSchedule("ข้าวเย็นนี้ 90 บาท"), false);
  // Standing on its own it is still a time.
  assert.equal(looksLikeSchedule("เที่ยงประชุม"), true);
  assert.equal(looksLikeSchedule("พรุ่งนี้เที่ยงกินข้าว"), true);

  assert.equal(single("ข้าวเที่ยง 80 บาท").amount, 80);
  assert.equal(single("มื้อเที่ยง 120 บาท").type, "expense");
});

test("calorie messages are refused this round", () => {
  assert.equal(parseMessage("ข้าวมันไก่ 600 แคล", NOW).feature, "calorie");
  assert.equal(parseMessage("ค ข้าวมันไก่ 600", NOW).feature, "calorie");
});

test("a message with both calories and money records the money", () => {
  const result = parseMessage("หมูกระทะ 800 แคล จ่าย 350 บาท", NOW);
  assert.equal(result.kind, "entries");
  assert.equal(result.ignoredCalories, true);
  assert.equal(result.entries[0].amount, 350);
});

test("commands", () => {
  assert.equal(parseMessage("สรุป", NOW).name, "summary_day");
  assert.equal(parseMessage("สรุปเดือน", NOW).name, "summary_month");
  assert.equal(parseMessage("ลบ", NOW).index, 1);
  assert.equal(parseMessage("ลบ 3", NOW).index, 3);
  assert.equal(parseMessage("แก้ 1500", NOW).amount, 1500);
  assert.equal(parseMessage("help", NOW).name, "help");
});

test("messages with no amount are reported as unparsed", () => {
  assert.equal(parseMessage("สวัสดี", NOW).kind, "unparsed");
  assert.equal(parseMessage("", NOW).kind, "unparsed");
});

test("date helpers", () => {
  assert.equal(localDate(NOW), "2026-08-23");
  assert.equal(localDate(NOW, -1), "2026-08-22");
  assert.equal(formatThaiDate("2026-08-23"), "23 ส.ค.");
  // 22:00 UTC is already the next day in Bangkok.
  assert.equal(localDate(new Date("2026-08-23T22:00:00Z")), "2026-08-24");
  assert.equal(bangkokIso(new Date("2026-08-23T22:00:00Z")), "2026-08-24T05:00:00+07:00");
});
