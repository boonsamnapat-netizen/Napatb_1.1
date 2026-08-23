/**
 * End-to-end tests for one conversation: message in, reply text out, ledger
 * updated. These run against real SQLite (see helpers/d1.js), so the queries,
 * the soft-delete filter and the per-user scoping are all genuinely exercised.
 */

import test from "node:test";
import assert from "node:assert/strict";

import { _respond } from "../src/index.js";
import { claimEvent } from "../src/db.js";
import { freshDb } from "./helpers/d1.js";

const NOW = new Date("2026-08-23T03:00:00Z"); // 10:00 Bangkok
const USER = "Uaaaaaaaaaaaaaaa";
const OTHER = "Ubbbbbbbbbbbbbbb";

/** Send one message as `owner` and return the bot's reply. */
function say(env, text, owner = USER, now = NOW) {
  return _respond(text, owner, now, now.toISOString(), env);
}

function setup() {
  return { DB: freshDb() };
}

test("an expense is saved and confirmed with a running total", async () => {
  const env = setup();

  const first = await say(env, "ข้าวเช้า 50");
  assert.match(first, /ข้าวเช้า/);
  assert.match(first, /50฿/);
  assert.match(first, /วันนี้ จ่าย 50฿/);
  // No unit, no verb — the reply should offer the correction.
  assert.match(first, /ไม่ใช่รายจ่าย\?/);

  const second = await say(env, "กาแฟ 120 บาท");
  assert.match(second, /วันนี้ จ่าย 170฿/);
  assert.doesNotMatch(second, /ไม่ใช่รายจ่าย\?/, "an explicit unit needs no nudge");
});

test("income and expense are totalled separately", async () => {
  const env = setup();
  await say(env, "จ่ายค่าไฟ 1,200 บาท");
  const reply = await say(env, "ได้เงินเดือน 30000");
  assert.match(reply, /จ่าย 1,200฿/);
  assert.match(reply, /รับ 30,000฿/);
});

test("two items in one message are saved as two entries", async () => {
  const env = setup();
  const reply = await say(env, "ค่าไฟ 1200 บาท กับค่าน้ำ 300 บาท");
  assert.match(reply, /ค่าไฟ/);
  assert.match(reply, /ค่าน้ำ/);
  assert.match(reply, /จ่าย 1,500฿/);
});

test("a back-dated entry reports that day's total, not today's", async () => {
  const env = setup();
  await say(env, "กาแฟ 120 บาท");
  const reply = await say(env, "เมื่อวานกินหมูกระทะ 350 บาท");
  assert.match(reply, /\(22 ส\.ค\.\)/, "the entry should be stamped with its own date");
  assert.match(reply, /22 ส\.ค\. จ่าย 350฿/, "totals should follow the entry's date");
});

test("the daily summary lists entries and the net", async () => {
  const env = setup();
  await say(env, "ข้าวเช้า 50 บาท");
  await say(env, "กาแฟ 120 บาท");
  await say(env, "ได้เงินเดือน 30000");

  const summary = await say(env, "สรุป");
  assert.match(summary, /23 ส\.ค\./);
  assert.match(summary, /จ่าย 170฿/);
  assert.match(summary, /รับ 30,000฿/);
  assert.match(summary, /คงเหลือสุทธิ 29,830฿/);
});

test("the monthly summary ranks categories", async () => {
  const env = setup();
  await say(env, "จ่ายค่าไฟ 1200 บาท");
  await say(env, "กาแฟ 120 บาท");
  await say(env, "ข้าวเที่ยง 80 บาท");

  const summary = await say(env, "สรุปเดือน");
  assert.match(summary, /ส\.ค\. 2026/);
  assert.match(summary, /จ่าย 1,400฿/);
  assert.match(summary, /ค่าน้ำค่าไฟ 1,200฿/);
  assert.match(summary, /อาหาร 200฿/);
});

test("ลบ removes the latest entry and the totals follow", async () => {
  const env = setup();
  await say(env, "ข้าวเช้า 50 บาท");
  await say(env, "กาแฟ 120 บาท");

  const deleted = await say(env, "ลบ");
  assert.match(deleted, /ลบแล้ว/);
  assert.match(deleted, /กาแฟ/);

  assert.match(await say(env, "สรุป"), /จ่าย 50฿/);
});

test("ลบ 2 removes the second-most-recent entry", async () => {
  const env = setup();
  await say(env, "ข้าวเช้า 50 บาท");
  await say(env, "กาแฟ 120 บาท");

  const deleted = await say(env, "ลบ 2");
  assert.match(deleted, /ข้าวเช้า/);
  assert.match(await say(env, "สรุป"), /จ่าย 120฿/);
});

test("ลบ on an empty ledger says so instead of failing", async () => {
  const env = setup();
  assert.match(await say(env, "ลบ"), /ไม่มีรายการ/);
});

test("แก้ corrects the amount and keeps the original readable", async () => {
  const env = setup();
  await say(env, "ค่าไฟ 1200 บาท");

  const amended = await say(env, "แก้ 1500");
  assert.match(amended, /1,200฿ → 1,500฿/);
  assert.match(await say(env, "สรุป"), /จ่าย 1,500฿/, "the old amount must not be counted twice");
});

test("one person's ledger never appears in another's summary", async () => {
  const env = setup();
  await say(env, "ข้าวเช้า 50 บาท", USER);
  await say(env, "กาแฟ 999 บาท", OTHER);

  assert.match(await say(env, "สรุป", USER), /จ่าย 50฿/);
  assert.match(await say(env, "สรุป", OTHER), /จ่าย 999฿/);
});

test("a redelivered webhook event is only counted once", async () => {
  const env = setup();
  const nowIso = NOW.toISOString();

  assert.equal(await claimEvent(env.DB, "evt-1", nowIso), true, "first delivery is new");
  assert.equal(await claimEvent(env.DB, "evt-1", nowIso), false, "redelivery must be skipped");
  assert.equal(await claimEvent(env.DB, "evt-2", nowIso), true);
});

test("schedule messages are declined without touching the ledger", async () => {
  const env = setup();
  assert.match(await say(env, "พรุ่งนี้ 2 ทุ่ม โทรหาแม่"), /ยังไม่รองรับ/);
  assert.match(await say(env, "สรุป"), /ยังไม่มีรายการ/);
});

test("a message carrying both units records both", async () => {
  const env = setup();
  const reply = await say(env, "หมูกระทะ 800 แคล จ่าย 350 บาท");
  assert.match(reply, /350฿/);
  assert.match(reply, /800 kcal/);

  const summary = await say(env, "สรุป");
  assert.match(summary, /จ่าย 350฿/);
  assert.match(summary, /กิน 800 kcal/);
});

test("an unreadable message gets a hint, not silence", async () => {
  const env = setup();
  const reply = await say(env, "สวัสดีครับ");
  assert.match(reply, /ไม่เจอตัวเลข/);
  assert.match(reply, /ช่วย/);
});

// ---- calories ---------------------------------------------------------------

test("a calorie entry is saved and the day's net is reported", async () => {
  const env = setup();
  assert.match(await say(env, "ข้าวมันไก่ 600 แคล"), /600 kcal/);
  const second = await say(env, "ค กาแฟเย็น 180");
  assert.match(second, /780 kcal/, "the day's intake should accumulate");
});

test("exercise subtracts from the day's calories", async () => {
  const env = setup();
  await say(env, "ข้าวมันไก่ 600 แคล");
  const reply = await say(env, "วิ่ง 30 นาที 300 แคล");
  assert.match(reply, /−300 kcal/);
  assert.match(reply, /วันนี้ 300 kcal/, "600 eaten minus 300 burned");
});

test("a figure typed once is remembered, and reused without a number", async () => {
  const env = setup();

  const first = await say(env, "ค ข้าวมันไก่ 600");
  assert.match(first, /จำ "ข้าวมันไก่" ไว้แล้ว/);

  const second = await say(env, "ค ข้าวมันไก่");
  assert.match(second, /600 kcal/);
  assert.match(second, /ใช้ค่าที่จำไว้/);
  assert.doesNotMatch(second, /จำ "ข้าวมันไก่" ไว้แล้ว/, "it should not re-announce what it knows");
});

test("an unknown dish is asked about rather than guessed", async () => {
  const env = setup();
  const reply = await say(env, "ค ส้มตำ");
  assert.match(reply, /ส้มตำ/);
  assert.match(reply, /ไม่มีตารางแคลอรี่/, "the bot must say it will not invent a figure");
  assert.match(await say(env, "สรุป"), /ยังไม่มีรายการ/, "nothing should have been saved");
});

test("จำ / ลืม / รายการจำ manage what the bot knows", async () => {
  const env = setup();

  assert.match(await say(env, "จำ ส้มตำ 120"), /จำไว้แล้ว 120 kcal/);
  assert.match(await say(env, "จำ ส้มตำ 150"), /แก้เป็น 150 kcal/);
  assert.match(await say(env, "รายการจำ"), /ส้มตำ 150 kcal/);

  // The remembered figure is what gets logged.
  assert.match(await say(env, "ค ส้มตำ"), /150 kcal/);

  assert.match(await say(env, "ลืม ส้มตำ"), /ลืม "ส้มตำ" แล้ว/);
  assert.match(await say(env, "ลืม ส้มตำ"), /ไม่เคยจำ/);
  assert.match(await say(env, "ค ส้มตำ"), /ไม่มีตารางแคลอรี่/);
});

test("a daily goal is shown against the running total", async () => {
  const env = setup();
  assert.match(await say(env, "เป้า"), /ยังไม่ได้ตั้งเป้า/);
  assert.match(await say(env, "เป้า 2000"), /2,000 kcal/);

  const reply = await say(env, "ข้าวมันไก่ 600 แคล");
  assert.match(reply, /600 \/ 2,000 kcal/);
  assert.match(reply, /เหลืออีก 1,400/);

  await say(env, "ค มื้อเย็น 1800");
  assert.match(await say(env, "สรุป"), /เกินมา 400/);
});

test("ลบ and แก้ work on calorie entries too", async () => {
  const env = setup();
  await say(env, "ข้าวมันไก่ 600 แคล");

  const amended = await say(env, "แก้ 700");
  assert.match(amended, /600 kcal → 700 kcal/, "the correction must stay in kcal, not become baht");
  assert.match(await say(env, "สรุป"), /กิน 700 kcal/);

  assert.match(await say(env, "ลบ"), /ลบแล้ว/);
  assert.match(await say(env, "สรุป"), /ยังไม่มีรายการ/);
});

test("money and calories are kept apart in the same day's summary", async () => {
  const env = setup();
  await say(env, "กาแฟ 120 บาท");
  await say(env, "ข้าวมันไก่ 600 แคล");

  const summary = await say(env, "สรุป");
  assert.match(summary, /จ่าย 120฿/);
  assert.match(summary, /กิน 600 kcal/);
  assert.doesNotMatch(summary, /600฿/, "calories must never be counted as money");
});

test("a coffee logged as money does not drag calories into the reply", async () => {
  const env = setup();
  await say(env, "ข้าวมันไก่ 600 แคล");
  const reply = await say(env, "กาแฟ 120 บาท");
  assert.match(reply, /จ่าย 120฿/);
  assert.doesNotMatch(reply, /kcal/);
});

test("the monthly summary averages calories over days actually logged", async () => {
  const env = setup();
  const yesterday = new Date("2026-08-22T03:00:00Z");
  await say(env, "ข้าวมันไก่ 600 แคล", USER, yesterday);
  await say(env, "ค มื้อเย็น 800");

  const summary = await say(env, "สรุปเดือน");
  assert.match(summary, /เฉลี่ย 700 kcal\/วัน/, "1,400 over two logged days");
  assert.match(summary, /2 วันที่บันทึก/);
});

test("ช่วย prints the usage guide", async () => {
  const env = setup();
  const reply = await say(env, "ช่วย");
  assert.match(reply, /วิธีใช้/);
  assert.match(reply, /สรุปเดือน/);
});

test("exercise figures are not memorised, because they depend on duration", async () => {
  const env = setup();
  const reply = await say(env, "วิ่ง 30 นาที 300 แคล");
  assert.doesNotMatch(reply, /จำ "วิ่ง" ไว้แล้ว/, "300 kcal is true of a 30 minute run, not of วิ่ง");
  assert.match(await say(env, "รายการจำ"), /ยังไม่ได้จำอะไรไว้/);

  // The user can still teach one on purpose.
  await say(env, "จำ วิ่ง 30 นาที 300");
  assert.match(await say(env, "รายการจำ"), /วิ่ง 30 นาที 300 kcal/);
});
