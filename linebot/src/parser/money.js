/**
 * Turn a short Thai message into an income or expense record.
 *
 * The guiding rule is the one the owner asked for: typing as little as possible
 * should still work. "ข้าวเช้า 50" is enough. Everything else — units, verbs,
 * day words — is optional and only sharpens the reading.
 *
 * When the message is genuinely ambiguous the parser does not stall asking a
 * question. It records its best guess and sets `needsConfirm`, so the reply can
 * offer a one-character correction. A bot that blocks on a question is useless
 * to someone typing while walking.
 */

import { thaiDigitsToArabic, findArabicNumbers, findThaiWordNumber } from "../lib/numbers.js";
import { findPastDayWord, bangkokIso, localDate } from "../lib/thaidate.js";

const MONEY_UNIT = /บาท|฿|\.-|บ\./g;
const CALORIE_UNIT = /แคลอรี่|แคล|kcal/gi;

// Words that fix the direction of the money, split by part of speech.
//
// Verbs are scaffolding — "จ่ายค่าไฟ" is better filed under "ค่าไฟ" — so they
// are stripped from the label. Nouns *are* the label ("เงินเดือน", "ค่าไฟ") and
// stay. A verb that overlaps a noun stays too, which is what keeps
// "ได้เงินเดือน" from being shortened to "เดือน".
const INCOME_NOUNS = ["เงินเดือน", "รายรับ", "โบนัส", "ปันผล", "ดอกเบี้ย"];
const INCOME_VERBS = ["ได้รับ", "ได้เงิน", "รับเงิน", "ขายได้", "ได้มา", "คืนเงิน", "ได้"];
const EXPENSE_NOUNS = ["รายจ่าย", "ค่า"];
const EXPENSE_VERBS = ["เสียเงิน", "จ่าย", "ซื้อ", "เติม"];

// Coarse buckets, matched against the label. Deliberately small: a wrong
// category is worse than no category, and the owner can always read the label.
const CATEGORIES = [
  ["food", ["ข้าว", "กิน", "อาหาร", "กาแฟ", "ชา", "ขนม", "น้ำ", "เครื่องดื่ม", "ก๋วยเตี๋ยว", "หมู", "ไก่", "ส้มตำ", "เบียร์"]],
  ["transport", ["แท็กซี่", "taxi", "grab", "วิน", "รถเมล์", "bts", "mrt", "น้ำมัน", "ค่ารถ", "ทางด่วน", "ที่จอดรถ"]],
  ["utilities", ["ค่าไฟ", "ค่าน้ำ", "ค่าเน็ต", "อินเทอร์เน็ต", "ค่าโทรศัพท์", "ค่าแก๊ส"]],
  ["housing", ["ค่าเช่า", "ค่าห้อง", "ค่าคอนโด", "ผ่อนบ้าน"]],
  ["health", ["ยา", "หมอ", "โรงพยาบาล", "คลินิก", "ประกัน"]],
  ["shopping", ["เสื้อ", "กางเกง", "รองเท้า", "ของใช้", "shopee", "lazada"]],
  ["salary", ["เงินเดือน", "โบนัส", "ปันผล", "ดอกเบี้ย"]],
];

function categorise(label) {
  const lowered = label.toLowerCase();
  for (const [name, keywords] of CATEGORIES) {
    if (keywords.some((keyword) => lowered.includes(keyword))) return name;
  }
  return null;
}

/** Collect [start,end) spans of every match, for removal from the label. */
function matchSpans(text, pattern) {
  const spans = [];
  pattern.lastIndex = 0;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    spans.push([match.index, match.index + match[0].length]);
    if (match[0].length === 0) pattern.lastIndex += 1;
  }
  return spans;
}

/** Remove the given spans and tidy the leftover whitespace — that is the label. */
function stripSpans(text, spans) {
  const sorted = [...spans].sort((a, b) => a[0] - b[0]);
  let out = "";
  let cursor = 0;
  for (const [start, end] of sorted) {
    if (start < cursor) continue;
    out += text.slice(cursor, start);
    cursor = end;
  }
  out += text.slice(cursor);
  return out.replace(/\s+/g, " ").trim();
}

/** Does a money unit sit immediately after (or just before) this number? */
function hasAdjacentUnit(text, span) {
  const after = text.slice(span[1], span[1] + 6);
  const before = text.slice(Math.max(0, span[0] - 2), span[0]);
  return /^\s*(?:บาท|฿|\.-|บ\.)/.test(after) || /฿\s*$/.test(before);
}

// `,(?!\d)` so a thousands separator never splits a message: "1,200" is one
// number, "ข้าว,น้ำ" is two items.
const CONNECTORS = /\s*(?:แล้วก็|และ|กับ|,(?!\d))\s*/;

/**
 * Split "ค่าไฟ 1200 บาท กับค่าน้ำ 300 บาท" into two messages.
 *
 * Only splits when every resulting segment carries exactly one number, which is
 * what keeps "ข้าวกับหมู 60" — one purchase whose name happens to contain กับ —
 * in one piece.
 */
function splitEntries(text) {
  const segments = text.split(CONNECTORS).map((s) => s.trim()).filter(Boolean);
  if (segments.length < 2) return [text];
  const allSingle = segments.every((segment) => findArabicNumbers(segment).length === 1);
  return allSingle ? segments : [text];
}

/** Every occurrence of any word in `words`, tagged with `meta`. */
function findMarkers(text, words, meta) {
  const found = [];
  for (const word of words) {
    let index = text.indexOf(word);
    while (index !== -1) {
      found.push({ word, start: index, end: index + word.length, ...meta });
      index = text.indexOf(word, index + 1);
    }
  }
  return found;
}

const overlaps = (a, b) => a.start < b.end && b.start < a.end;

/**
 * Read the direction of the money from the words used, and say which spans to
 * drop from the label.
 *
 * @returns {{direction:"income"|"expense"|null, removals:Array<[number,number]>}}
 */
function readDirection(text) {
  const nouns = [
    ...findMarkers(text, INCOME_NOUNS, { direction: "income" }),
    ...findMarkers(text, EXPENSE_NOUNS, { direction: "expense" }),
  ];
  const verbs = [
    ...findMarkers(text, INCOME_VERBS, { direction: "income" }),
    ...findMarkers(text, EXPENSE_VERBS, { direction: "expense" }),
  ];

  // Earliest word describes the message; on a tie the longer one is more
  // specific ("ขายได้" over the "ได้" inside it).
  const all = [...nouns, ...verbs].sort(
    (a, b) => a.start - b.start || b.end - b.start - (a.end - a.start),
  );
  if (all.length === 0) return { direction: null, removals: [] };

  const removals = verbs
    .filter((verb) => !nouns.some((noun) => overlaps(verb, noun)))
    .map((verb) => [verb.start, verb.end]);

  return { direction: all[0].direction, removals };
}

/**
 * Parse one segment into a record.
 * @returns {object|null} null when there is no amount to record.
 */
function parseOne(segment, now) {
  const text = thaiDigitsToArabic(segment);
  const removals = [];

  const day = findPastDayWord(text);
  const offsetDays = day ? day.offsetDays : 0;
  if (day) removals.push([day.start, day.end]);

  // An explicit sign wins over any keyword: "+30000 โบนัส", "-250 ข้าว".
  const signed = /(^|\s)([+-])\s*(?=\d)/.exec(text);
  let direction = null;
  if (signed) {
    direction = signed[2] === "+" ? "income" : "expense";
    const start = signed.index + signed[1].length;
    removals.push([start, start + signed[0].length - signed[1].length]);
  }

  const numbers = findArabicNumbers(text);
  let amount = null;
  let amountSpan = null;

  if (numbers.length > 0) {
    // A number wearing a unit is the amount, whatever else is in the message.
    const withUnit = numbers.find((n) => hasAdjacentUnit(text, [n.start, n.end]));
    const chosen = withUnit ?? numbers[numbers.length - 1];
    amount = chosen.value;
    amountSpan = [chosen.start, chosen.end];
  } else {
    const spelled = findThaiWordNumber(text);
    if (spelled) {
      amount = spelled.value;
      amountSpan = [spelled.start, spelled.end];
    }
  }

  if (amount === null || amount <= 0) return null;
  removals.push(amountSpan);

  const unitSpans = matchSpans(text, MONEY_UNIT);
  removals.push(...unitSpans);

  const read = readDirection(text);
  if (direction === null) direction = read.direction;
  removals.push(...read.removals);

  const hadDirectionWord = direction !== null;
  if (direction === null) direction = "expense";

  const label = stripSpans(text, removals) || segment.trim();

  // No unit and no verb: "ข้าวมันไก่ 60" could just as well be calories. Record
  // it as an expense — by far the more common case — and flag it so the reply
  // can offer the flip.
  const needsConfirm = unitSpans.length === 0 && !hadDirectionWord;

  return {
    type: direction,
    amount,
    currency: "THB",
    label,
    category: categorise(label),
    occurredAt: bangkokIso(now, offsetDays),
    localDate: localDate(now, offsetDays),
    needsConfirm,
    parser: "regex",
    raw: segment.trim(),
  };
}

/**
 * Parse a money message into one or more records.
 * @returns {Array<object>} empty when nothing recordable was found.
 */
export function parseMoney(text, now) {
  const segments = splitEntries(text);
  const entries = [];
  for (const segment of segments) {
    const entry = parseOne(segment, now);
    if (entry) entries.push(entry);
  }
  return entries;
}

export const _internals = { categorise, stripSpans, splitEntries };
