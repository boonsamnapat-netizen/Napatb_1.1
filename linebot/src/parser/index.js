/**
 * Message dispatcher: decides what a line of Thai text is asking for.
 *
 * Commands first, then the routing rules below, then money as the default.
 * The order of those rules is the whole design:
 *
 *   An explicit unit always wins. บาท means money, แคล means calories, and a
 *   message carrying both is two records, not a choice between them.
 *
 *   A money unit outranks an exercise word, because "เดินไปซื้อของ 50 บาท" is
 *   shopping. Only once no money unit is in sight does วิ่ง / ว่ายน้ำ route a
 *   message to the calorie parser.
 *
 *   Schedules are checked late but still ahead of the money default, so
 *   "8 โมง ประชุม" is refused instead of being filed as an 8 baht expense.
 */

import { parseMoney } from "./money.js";
import { parseCalorie, hasCalorieWord, hasExerciseWord } from "./calorie.js";
import { looksLikeSchedule } from "../lib/thaidate.js";
import { thaiDigitsToArabic } from "../lib/numbers.js";

const MONEY_UNIT = /บาท|฿|\.-|บ\./;

/** `ค` as a leading word forces the calorie reading of an ambiguous message. */
const FORCE_CALORIE = /^ค(\s+.*)?$/;
/** `บ` does the same for money, for a dish whose name the bot has memorised. */
const FORCE_MONEY = /^บ(\s+.*)?$/;

const NUMBER = String.raw`[\d,\.]+`;

const COMMANDS = [
  [/^(?:สรุปเดือน|สรุป\s*เดือน|เดือนนี้|\/month)\s*$/i, () => ({ kind: "command", name: "summary_month" })],
  [/^(?:สรุป|สรุปวันนี้|วันนี้|\/summary)\s*$/i, () => ({ kind: "command", name: "summary_day" })],
  [/^(?:ลบ|\/delete)\s*(\d*)\s*$/i, (m) => ({ kind: "command", name: "delete", index: m[1] ? Number(m[1]) : 1 })],
  [
    new RegExp(String.raw`^(?:แก้|\/edit)\s+(${NUMBER})\s*(?:บาท|฿|แคล|kcal)?\s*$`, "i"),
    (m) => ({ kind: "command", name: "amend", amount: toNumber(m[1]) }),
  ],
  [
    new RegExp(String.raw`^(?:จำ|จด)\s+(.+?)\s+(${NUMBER})\s*(?:แคล|kcal)?\s*$`, "i"),
    (m) => ({ kind: "command", name: "remember", label: m[1].trim(), kcal: toNumber(m[2]) }),
  ],
  [/^(?:ลืม|ลบที่จำ)\s+(.+?)\s*$/i, (m) => ({ kind: "command", name: "forget", label: m[1].trim() })],
  [/^(?:รายการจำ|ที่จำไว้|จำอะไรบ้าง|จำไว้)\s*$/i, () => ({ kind: "command", name: "memories" })],
  [
    new RegExp(String.raw`^(?:เป้า|เป้าหมาย)\s*(${NUMBER})?\s*(?:แคล|kcal)?\s*$`, "i"),
    (m) => ({ kind: "command", name: "goal", kcal: m[1] ? toNumber(m[1]) : null }),
  ],
  [/^(?:ช่วย|ช่วยเหลือ|วิธีใช้|help|\/help|\?)\s*$/i, () => ({ kind: "command", name: "help" })],
];

const toNumber = (text) => Number(text.replace(/,/g, ""));

/**
 * @param {string} rawText message text as typed
 * @param {Date} now current instant
 * @param {(name:string) => Promise<{kcal:number}|null>} recall dish lookup
 * @returns {Promise<object>} one of:
 *   {kind:"command", name, ...}
 *   {kind:"entries", entries:[...]}
 *   {kind:"need_figure", label, direction}  — calories unknown, ask for them
 *   {kind:"unsupported", feature:"task"}
 *   {kind:"unparsed"}
 */
export async function parseMessage(rawText, now, recall = async () => null) {
  const text = thaiDigitsToArabic(String(rawText ?? "")).trim();
  if (!text) return { kind: "unparsed" };

  for (const [pattern, build] of COMMANDS) {
    const match = pattern.exec(text);
    if (match) return build(match);
  }

  const forcedCalorie = FORCE_CALORIE.exec(text);
  if (forcedCalorie) return calorieResult(forcedCalorie[1] ?? "", now, recall);

  const forcedMoney = FORCE_MONEY.exec(text);
  if (forcedMoney) return moneyResult(forcedMoney[1] ?? "", now);

  const hasMoney = MONEY_UNIT.test(text);
  const hasCalorie = hasCalorieWord(text);

  // Both units named: record both halves rather than picking a winner.
  if (hasMoney && hasCalorie) {
    const [money, calorie] = await Promise.all([
      Promise.resolve(parseMoney(text, now)),
      parseCalorie(text, now, recall),
    ]);
    const entries = [...money];
    if (!calorie.needsFigure) entries.push(calorie);
    return entries.length > 0 ? { kind: "entries", entries } : { kind: "unparsed" };
  }

  if (hasCalorie) return calorieResult(text, now, recall);
  if (hasMoney) return moneyResult(text, now);

  if (looksLikeSchedule(text)) return { kind: "unsupported", feature: "task" };
  if (hasExerciseWord(text)) return calorieResult(text, now, recall);

  return moneyResult(text, now);
}

async function calorieResult(text, now, recall) {
  const trimmed = text.trim();
  if (!trimmed) return { kind: "unparsed" };
  const entry = await parseCalorie(trimmed, now, recall);
  if (entry.needsFigure) {
    return { kind: "need_figure", label: entry.label, direction: entry.direction };
  }
  return { kind: "entries", entries: [entry] };
}

function moneyResult(text, now) {
  const trimmed = text.trim();
  const entries = trimmed ? parseMoney(trimmed, now) : [];
  return entries.length > 0 ? { kind: "entries", entries } : { kind: "unparsed" };
}
