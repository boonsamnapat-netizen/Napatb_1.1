/**
 * Turn a short Thai message into a calorie record.
 *
 * Food eaten counts up, exercise counts down, and the day's figure is the
 * difference. The parser never invents a calorie figure: if the message does not
 * carry one and the bot has not been told one before, it says so and asks. A
 * made-up number would look exactly like a measured one in next month's total.
 *
 * The number nearest a calorie unit wins. That matters more here than in the
 * money parser because a workout carries two numbers — "วิ่ง 30 นาที 300 แคล" is
 * thirty minutes and three hundred calories, and reading the wrong one is a
 * tenfold error.
 */

import { thaiDigitsToArabic, findArabicNumbers, findThaiWordNumber } from "../lib/numbers.js";
import { findPastDayWord, bangkokIso, localDate } from "../lib/thaidate.js";

const CALORIE_UNIT = /แคลอรี่|แคล|kcal|cal(?![a-z])/gi;

// Exercise burns; everything else is assumed to be food going in.
const BURN_WORDS = [
  "ออกกำลังกาย", "ออกกำลัง", "ปั่นจักรยาน", "กระโดดเชือก", "ว่ายน้ำ",
  "แอโรบิก", "จักรยาน", "ฟิตเนส", "วิ่ง", "เดิน", "โยคะ", "เวท", "ยิม",
  "เต้น", "เผา",
];

// The subset strong enough to send a message down the calorie path on its own.
// เดิน and เต้น are left out: "เดินไปซื้อของ 50" is shopping, not cardio. They
// still set the direction once the message is known to be about calories.
const BURN_ROUTING = [
  "ออกกำลังกาย", "ออกกำลัง", "ปั่นจักรยาน", "กระโดดเชือก", "ว่ายน้ำ",
  "แอโรบิก", "ฟิตเนส", "วิ่ง", "โยคะ", "ยิม", "เผา",
];
const INTAKE_WORDS = ["กิน", "ทาน", "ดื่ม", "มื้อ"];

// Words the label reads better without.
const STRIP_WORDS = [...INTAKE_WORDS, "เผา"];

const DURATION = /(\d+(?:\.\d+)?)\s*(นาที|ชั่วโมง|ชม\.?)/g;

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

/** Is a calorie unit sitting right after this number? */
function hasCalorieUnit(text, span) {
  return /^\s*(?:แคลอรี่|แคล|kcal|cal(?![a-z]))/i.test(text.slice(span[1], span[1] + 10));
}

/** Minutes of exercise, and the spans to keep out of the calorie hunt. */
function readDuration(text) {
  DURATION.lastIndex = 0;
  let minutes = null;
  const spans = [];
  let match;
  while ((match = DURATION.exec(text)) !== null) {
    const value = Number.parseFloat(match[1]);
    const isHours = match[2].startsWith("ชั่วโมง") || match[2].startsWith("ชม");
    minutes = (minutes ?? 0) + (isHours ? value * 60 : value);
    spans.push([match.index, match.index + match[0].length]);
  }
  return { minutes, spans };
}

const overlapsAny = (span, spans) =>
  spans.some(([start, end]) => span[0] < end && start < span[1]);

/**
 * Parse a calorie message.
 *
 * @param {string} rawText
 * @param {Date} now
 * @param {(name:string) => {kcal:number, direction:string}|null} recall
 *        looks a dish up in what the user has already taught the bot
 * @returns {object} an entry, or {needsFigure:true, label} when the calories are
 *          not known and cannot be guessed
 */
export async function parseCalorie(rawText, now, recall = async () => null) {
  const text = thaiDigitsToArabic(rawText).trim();
  const removals = [];

  const day = findPastDayWord(text);
  const offsetDays = day ? day.offsetDays : 0;
  if (day) removals.push([day.start, day.end]);

  const burnWord = BURN_WORDS.find((word) => text.includes(word));
  const direction = burnWord ? "burn" : "intake";

  const duration = readDuration(text);
  removals.push(...duration.spans);

  const unitSpans = matchSpans(text, CALORIE_UNIT);
  removals.push(...unitSpans);

  // Pick the calorie figure, never a duration.
  const numbers = findArabicNumbers(text).filter(
    (n) => !overlapsAny([n.start, n.end], duration.spans),
  );
  let kcal = null;
  const withUnit = numbers.find((n) => hasCalorieUnit(text, [n.start, n.end]));
  const chosen = withUnit ?? numbers[numbers.length - 1];
  if (chosen) {
    kcal = chosen.value;
    removals.push([chosen.start, chosen.end]);
  } else {
    const spelled = findThaiWordNumber(text);
    if (spelled) {
      kcal = spelled.value;
      removals.push([spelled.start, spelled.end]);
    }
  }

  for (const word of STRIP_WORDS) {
    const index = text.indexOf(word);
    if (index !== -1) removals.push([index, index + word.length]);
  }

  const label = stripSpans(text, removals) || text;
  let fromMemory = false;

  // Nothing in the message — fall back to what the bot has been taught.
  if (kcal === null) {
    const remembered = await recall(label);
    if (remembered) {
      kcal = remembered.kcal;
      fromMemory = true;
    } else {
      return { needsFigure: true, label, direction };
    }
  }

  return {
    type: "calorie",
    direction,
    kcal,
    label,
    durationMin: duration.minutes,
    occurredAt: bangkokIso(now, offsetDays),
    localDate: localDate(now, offsetDays),
    needsConfirm: false,
    fromMemory,
    parser: "regex",
    raw: rawText.trim(),
  };
}

/** Does the message carry an explicit calorie unit (แคล / kcal)? */
export function hasCalorieWord(text) {
  CALORIE_UNIT.lastIndex = 0;
  return CALORIE_UNIT.test(text);
}

/** Does it name an activity clear enough to route down the calorie path? */
export function hasExerciseWord(text) {
  return BURN_ROUTING.some((word) => text.includes(word));
}
