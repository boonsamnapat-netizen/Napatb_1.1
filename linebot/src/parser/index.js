/**
 * Message dispatcher: decides what a line of Thai text is asking for.
 *
 * Commands are checked first, then the two "not this round" guards, then the
 * money parser. The guards matter more than they look: without them "8 โมง
 * ประชุม" reaches the money parser and lands in the ledger as an 8 baht
 * expense. Refusing loudly beats recording quietly.
 */

import { parseMoney } from "./money.js";
import { looksLikeSchedule } from "../lib/thaidate.js";
import { thaiDigitsToArabic } from "../lib/numbers.js";

const CALORIE_UNIT = /แคลอรี่|แคล|kcal/i;
const MONEY_UNIT = /บาท|฿|\.-|บ\./;

/** `ค` on its own, as a leading word, forces the calorie reading. */
const FORCE_CALORIE = /^ค(?:\s|$)/;

const COMMANDS = [
  [/^(?:สรุปเดือน|สรุป\s*เดือน|เดือนนี้|\/month)\s*$/i, () => ({ kind: "command", name: "summary_month" })],
  [/^(?:สรุป|สรุปวันนี้|วันนี้|\/summary)\s*$/i, () => ({ kind: "command", name: "summary_day" })],
  [/^(?:ลบ|\/delete)\s*(\d*)\s*$/i, (m) => ({ kind: "command", name: "delete", index: m[1] ? Number(m[1]) : 1 })],
  [/^(?:แก้|\/edit)\s+([\d,\.]+)\s*(?:บาท|฿)?\s*$/i, (m) => ({ kind: "command", name: "amend", amount: Number(m[1].replace(/,/g, "")) })],
  [/^(?:ช่วย|ช่วยเหลือ|วิธีใช้|help|\/help|\?)\s*$/i, () => ({ kind: "command", name: "help" })],
];

/**
 * @param {string} rawText message text as typed
 * @param {Date} now current instant
 * @returns {{kind:string}} one of:
 *   {kind:"command", name, ...}
 *   {kind:"entries", entries:[...], ignoredCalories:boolean}
 *   {kind:"unsupported", feature:"calorie"|"task"}
 *   {kind:"unparsed"}
 */
export function parseMessage(rawText, now) {
  const text = thaiDigitsToArabic(String(rawText ?? "")).trim();
  if (!text) return { kind: "unparsed" };

  for (const [pattern, build] of COMMANDS) {
    const match = pattern.exec(text);
    if (match) return build(match);
  }

  if (FORCE_CALORIE.test(text)) return { kind: "unsupported", feature: "calorie" };

  const hasMoney = MONEY_UNIT.test(text);
  const hasCalorie = CALORIE_UNIT.test(text);

  // A schedule that also names an amount ("เตือนวันที่ 5 จ่ายบัตร 4500") is
  // still a reminder — the amount is part of the reminder, not a purchase.
  if (looksLikeSchedule(text)) return { kind: "unsupported", feature: "task" };
  if (hasCalorie && !hasMoney) return { kind: "unsupported", feature: "calorie" };

  const entries = parseMoney(text, now);
  if (entries.length === 0) return { kind: "unparsed" };

  return { kind: "entries", entries, ignoredCalories: hasCalorie };
}
