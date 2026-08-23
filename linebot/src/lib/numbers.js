/**
 * Thai number normalisation.
 *
 * Turns the many ways a Thai speaker writes a quantity into a plain JS number:
 * Thai digits (๕๐๐), thousands separators (1,200), scale suffixes (1.2k, 2หมื่น)
 * and spelled-out numerals (สองร้อยห้าสิบ).
 *
 * Note on word boundaries: Thai text has no spaces, and Python/JS `\b` treats
 * Thai letters as word characters, so `\b` fires in the wrong places. Every
 * pattern here is written to work without it — "85บาท" must parse as well as
 * "85 บาท".
 */

const THAI_DIGITS = "๐๑๒๓๔๕๖๗๘๙";

/** ๕๐๐ -> 500. Leaves every other character untouched. */
export function thaiDigitsToArabic(text) {
  return text.replace(/[๐-๙]/g, (c) => String(THAI_DIGITS.indexOf(c)));
}

// Spelled-out numerals. `เอ็ด` is the "one" used in 11/21/31…, `ยี่` the "two"
// used only in ยี่สิบ.
const WORD_DIGITS = {
  ศูนย์: 0, หนึ่ง: 1, เอ็ด: 1, สอง: 2, ยี่: 2, สาม: 3, สี่: 4,
  ห้า: 5, หก: 6, เจ็ด: 7, แปด: 8, เก้า: 9,
};
const WORD_SCALES = { สิบ: 10, ร้อย: 100, พัน: 1000, หมื่น: 10000, แสน: 100000, ล้าน: 1000000 };

// Longest-first so `หนึ่ง` is tried before `หก`, `แสน` before `สาม`, etc.
const WORD_TOKENS = [...Object.keys(WORD_DIGITS), ...Object.keys(WORD_SCALES)]
  .sort((a, b) => b.length - a.length);

const WORD_RUN = new RegExp(`(?:${WORD_TOKENS.join("|")})+`, "g");

/** Split a run of numeral words into tokens, or null if it does not tokenise cleanly. */
function tokenizeWords(run) {
  const tokens = [];
  let i = 0;
  outer: while (i < run.length) {
    for (const tok of WORD_TOKENS) {
      if (run.startsWith(tok, i)) {
        tokens.push(tok);
        i += tok.length;
        continue outer;
      }
    }
    return null;
  }
  return tokens;
}

/** ["สอง","ร้อย","ห้า","สิบ"] -> 250 */
function foldTokens(tokens) {
  let total = 0;
  let current = 0;
  for (const tok of tokens) {
    if (tok in WORD_DIGITS) {
      current = WORD_DIGITS[tok];
      continue;
    }
    const scale = WORD_SCALES[tok];
    // A bare scale word means one of it: สิบ = 10, ร้อย = 100.
    if (current === 0) current = 1;
    if (scale === 1000000) {
      total = (total + current) * scale;
    } else {
      total += current * scale;
    }
    current = 0;
  }
  return total + current;
}

/**
 * Find a spelled-out Thai number in `text`.
 *
 * Only runs of two or more numeral tokens count. A single token is rejected on
 * purpose: Thai has no spaces, so a lone `แสน` is far more likely to be part of
 * แสนแพง ("terribly expensive") than to mean 100,000 — and `สี่` is usually
 * สี่แยก, not the digit 4. Two tokens in a row (สามหมื่น, หนึ่งพัน, ห้าสิบ) are
 * almost never a coincidence.
 *
 * @returns {{value:number, start:number, end:number}|null}
 */
export function findThaiWordNumber(text) {
  WORD_RUN.lastIndex = 0;
  let match;
  while ((match = WORD_RUN.exec(text)) !== null) {
    const tokens = tokenizeWords(match[0]);
    if (!tokens || tokens.length < 2) continue;
    const value = foldTokens(tokens);
    if (value > 0) {
      return { value, start: match.index, end: match.index + match[0].length };
    }
  }
  return null;
}

// Scale suffixes that may follow an Arabic number: 1.2k, 2หมื่น, 3 พัน.
const SUFFIX_SCALES = [
  ["ล้าน", 1000000], ["แสน", 100000], ["หมื่น", 10000], ["พัน", 1000],
  ["k", 1000], ["K", 1000], ["m", 1000000], ["M", 1000000],
];

// A number with optional thousands separators and decimals, plus an optional
// scale suffix. Deliberately no \b — Thai letters may sit flush against it.
const ARABIC_NUMBER = new RegExp(
  String.raw`(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(` +
    SUFFIX_SCALES.map(([s]) => s).join("|") +
    String.raw`)?`,
  "g",
);

/**
 * Find every Arabic-digit number in `text`, resolving separators and suffixes.
 * Call `thaiDigitsToArabic` first if the text may contain ๐-๙.
 *
 * @returns {Array<{value:number, start:number, end:number, hadSuffix:boolean}>}
 */
export function findArabicNumbers(text) {
  const out = [];
  ARABIC_NUMBER.lastIndex = 0;
  let match;
  while ((match = ARABIC_NUMBER.exec(text)) !== null) {
    const raw = match[1].replace(/,/g, "");
    let value = Number.parseFloat(raw);
    if (!Number.isFinite(value)) continue;
    const suffix = match[2];
    if (suffix) {
      const scale = SUFFIX_SCALES.find(([s]) => s === suffix);
      value *= scale[1];
    }
    out.push({
      value,
      start: match.index,
      end: match.index + match[0].length,
      hadSuffix: Boolean(suffix),
    });
  }
  return out;
}
