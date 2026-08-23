/**
 * Thai dates and the Thai clock.
 *
 * Bangkok is a fixed UTC+07:00 — Thailand has never observed daylight saving —
 * so the offset is a constant rather than a timezone database lookup.
 *
 * Round 1 (income/expense) needs only *past* day words: "เมื่อวานกินข้าว 50".
 * The clock patterns below are here to *detect* a time, not to resolve one:
 * without them "8 โมง ประชุม" would fall through to the money parser and be
 * recorded as an 8 baht expense. Detection lets the bot say "not yet" instead
 * of silently saving the wrong thing. Resolving a time to a due date belongs
 * to the to-do round.
 */

export const BANGKOK_OFFSET_MIN = 7 * 60;

const THAI_MONTHS_ABBR = [
  "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
  "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
];

/** Wall-clock parts in Bangkok for an instant. */
function bangkokParts(date) {
  const shifted = new Date(date.getTime() + BANGKOK_OFFSET_MIN * 60_000);
  return {
    year: shifted.getUTCFullYear(),
    month: shifted.getUTCMonth(),
    day: shifted.getUTCDate(),
    hour: shifted.getUTCHours(),
    minute: shifted.getUTCMinutes(),
  };
}

const pad = (n) => String(n).padStart(2, "0");

/** "2026-08-23" — the Bangkok calendar date, used to group daily/monthly totals. */
export function localDate(date, offsetDays = 0) {
  const { year, month, day } = bangkokParts(date);
  const shifted = new Date(Date.UTC(year, month, day + offsetDays));
  return `${shifted.getUTCFullYear()}-${pad(shifted.getUTCMonth() + 1)}-${pad(shifted.getUTCDate())}`;
}

/**
 * ISO-8601 with an explicit +07:00 offset, at the same wall-clock time of day
 * but `offsetDays` away. Storing the offset (rather than bare UTC) keeps the
 * 00:00–07:00 window from landing on the previous day when totals are grouped.
 */
export function bangkokIso(date, offsetDays = 0) {
  const { year, month, day, hour, minute } = bangkokParts(date);
  const shifted = new Date(Date.UTC(year, month, day + offsetDays));
  return (
    `${shifted.getUTCFullYear()}-${pad(shifted.getUTCMonth() + 1)}-${pad(shifted.getUTCDate())}` +
    `T${pad(hour)}:${pad(minute)}:00+07:00`
  );
}

/** "2026-08-23" -> "23 ส.ค." for replies. */
export function formatThaiDate(isoDate) {
  const [year, month, day] = isoDate.split("-").map(Number);
  return `${day} ${THAI_MONTHS_ABBR[month - 1]}`;
}

/** "2026-08" -> "ส.ค. 2026" */
export function formatThaiMonth(isoMonth) {
  const [year, month] = isoMonth.split("-").map(Number);
  return `${THAI_MONTHS_ABBR[month - 1]} ${year}`;
}

// Past and present day words, longest first so "เมื่อวานซืน" wins over "เมื่อวาน".
const PAST_DAY_WORDS = [
  ["เมื่อวานซืน", -2],
  ["วานซืน", -2],
  ["เมื่อวานนี้", -1],
  ["เมื่อวาน", -1],
  ["วานนี้", -1],
  ["เมื่อคืน", -1],
  ["วันนี้", 0],
  ["เช้านี้", 0],
  ["วันนี้", 0],
];

/**
 * Find a past/today day word and how many days back it points.
 * @returns {{offsetDays:number, start:number, end:number}|null}
 */
export function findPastDayWord(text) {
  for (const [word, offsetDays] of PAST_DAY_WORDS) {
    const index = text.indexOf(word);
    if (index !== -1) {
      return { offsetDays, start: index, end: index + word.length };
    }
  }
  return null;
}

// Words that point at a future moment, or ask to be reminded. Anything matching
// these is a to-do, not a purchase.
const FUTURE_OR_REMINDER = [
  /พรุ่งนี้/,
  /มะรืน/,
  /เตือน/,
  /ทุกวัน/,
  /ทุกสัปดาห์/,
  /ทุกเดือน/,
  /ทุกวัน(?:จันทร์|อังคาร|พุธ|พฤหัส|ศุกร์|เสาร์|อาทิตย์)/,
  /วัน(?:จันทร์|อังคาร|พุธ|พฤหัส|ศุกร์|เสาร์|อาทิตย์)/,
  /(?:จันทร์|อังคาร|พุธ|พฤหัส|ศุกร์|เสาร์|อาทิตย์)หน้า/,
  /สัปดาห์หน้า|อาทิตย์หน้า|เดือนหน้า/,
  /สิ้นเดือน/,
];

// Thai clock expressions.
//
// Two lookbehinds do the heavy lifting, both for the same reason — Thai is
// written without spaces, so a time word is constantly a substring of an
// ordinary one:
//
//   `โมง`  is inside ชั่วโมง, so "วิ่ง 2 ชั่วโมง" would read as 02:00.
//   `เที่ยง` is inside ข้าวเที่ยง / มื้อเที่ยง, so lunch would read as noon.
//
// The rule for the second case: a time word glued to the end of another Thai
// word belongs to that word. "เที่ยงประชุม" is noon; "ข้าวเที่ยง 80" is lunch.
// Standalone reminders still get caught, because those carry a day word
// ("พรุ่งนี้เที่ยง") that matches on its own.
const NOT_AFTER_THAI = String.raw`(?<![฀-๿])`;

const CLOCK_PATTERNS = [
  /\d{1,2}[:.]\d{2}\s*น\.?/,
  /\d{1,2}:\d{2}/,
  /\d{1,2}\s*นาฬิกา/,
  /ตี\s*\d{1,2}/,
  /\d{1,2}\s*ทุ่ม/,
  /บ่าย\s*(?:โมง|\d{1,2})/,
  new RegExp(`${NOT_AFTER_THAI}(?:เที่ยงคืน|เที่ยงวัน|เที่ยง)`),
  /\d{1,2}\s*(?<!ชั่ว)โมง/,
  /(?<!ชั่ว)โมง(?:เช้า|เย็น)/,
  new RegExp(`${NOT_AFTER_THAI}(?:เช้า|สาย|บ่าย|เย็น|ค่ำ|ดึก)\\s*นี้`),
];

/**
 * True when the message is about *when to do something* rather than what was
 * spent. Used to keep to-do messages out of the expense ledger until the to-do
 * round lands.
 */
export function looksLikeSchedule(text) {
  return (
    FUTURE_OR_REMINDER.some((re) => re.test(text)) ||
    CLOCK_PATTERNS.some((re) => re.test(text))
  );
}
