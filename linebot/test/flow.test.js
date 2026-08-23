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

test("schedule and calorie messages are declined without touching the ledger", async () => {
  const env = setup();
  assert.match(await say(env, "พรุ่งนี้ 2 ทุ่ม โทรหาแม่"), /ยังไม่รองรับ/);
  assert.match(await say(env, "ข้าวมันไก่ 600 แคล"), /แคลอรี่/);
  assert.match(await say(env, "สรุป"), /ยังไม่มีรายการ/);
});

test("a message carrying both calories and money records the money and says so", async () => {
  const env = setup();
  const reply = await say(env, "หมูกระทะ 800 แคล จ่าย 350 บาท");
  assert.match(reply, /350฿/);
  assert.match(reply, /แคลอรี่ยังไม่รองรับ/);
});

test("an unreadable message gets a hint, not silence", async () => {
  const env = setup();
  const reply = await say(env, "สวัสดีครับ");
  assert.match(reply, /ไม่เจอจำนวนเงิน/);
  assert.match(reply, /ช่วย/);
});

test("ช่วย prints the usage guide", async () => {
  const env = setup();
  const reply = await say(env, "ช่วย");
  assert.match(reply, /วิธีใช้/);
  assert.match(reply, /สรุปเดือน/);
});
