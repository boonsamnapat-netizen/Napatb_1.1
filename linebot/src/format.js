/**
 * Thai reply text.
 *
 * Three rules hold the replies together:
 *
 * 1. Confirm what was understood, not what was typed. Echoing "23 ส.ค. 350฿"
 *    lets a misread be spotted at a glance; echoing the original message back
 *    proves nothing.
 * 2. Show the running total. The reason to log a purchase is to know where the
 *    month stands, so the answer to every entry is the new total.
 * 3. Offer the fix on one line, and only when the reading was actually
 *    uncertain. A hint under every message is noise nobody reads.
 */

import { formatThaiDate, formatThaiMonth } from "./lib/thaidate.js";

/** 1234.5 -> "1,234.50" · 1200 -> "1,200" */
export function money(value) {
  const rounded = Math.round(value * 100) / 100;
  const fixed = Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(2);
  const [whole, decimals] = fixed.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return decimals ? `${grouped}.${decimals}` : grouped;
}

const ICON = { expense: "💸", income: "💰" };

/**
 * Confirmation for freshly saved entries, plus the running totals for the day
 * they landed on.
 *
 * The totals follow the entry, not the clock: logging yesterday's dinner should
 * show yesterday's total, since today's did not move.
 *
 * @param {Array<object>} entries parsed entries as saved
 * @param {{expense:number, income:number}} totals for `totalsDate`, after saving
 * @param {string} totalsDate the Bangkok date those totals cover
 * @param {string} todayDate today in Bangkok
 */
export function savedEntries(entries, totals, totalsDate, todayDate) {
  const lines = entries.map((entry) => {
    const sign = entry.type === "income" ? "+" : "";
    const label = entry.label || "(ไม่มีชื่อ)";
    const when = entry.localDate === todayDate ? "" : ` (${formatThaiDate(entry.localDate)})`;
    return `${ICON[entry.type]} ${label} ${sign}${money(entry.amount)}฿${when}`;
  });

  const dayName = totalsDate === todayDate ? "วันนี้" : formatThaiDate(totalsDate);
  lines.push(`— ${dayName} จ่าย ${money(totals.expense)}฿ · รับ ${money(totals.income)}฿`);

  // Only nudge when the reading really was a coin flip.
  if (entries.some((entry) => entry.needsConfirm)) {
    lines.push("↳ ไม่ใช่รายจ่าย? พิมพ์ `ลบ` แล้วพิมพ์ใหม่พร้อมหน่วย เช่น `กาแฟ 120 บาท`");
  }
  return lines.join("\n");
}

export function caloriesIgnored() {
  return "หมายเหตุ: ตอนนี้บันทึกเฉพาะเงิน ส่วนแคลอรี่ยังไม่รองรับ (รอบถัดไป)";
}

export function deleted(row) {
  const sign = row.type === "income" ? "+" : "";
  return `🗑 ลบแล้ว: ${row.label || row.raw} ${sign}${money(row.amount)}฿`;
}

export function amended(row, oldAmount) {
  return `✏️ แก้แล้ว: ${row.label || row.raw} ${money(oldAmount)}฿ → ${money(row.amount)}฿`;
}

export function nothingToDelete() {
  return "ไม่มีรายการให้ลบครับ";
}

export function daySummary(summary, localDate) {
  if (summary.count === 0) return `📊 ${formatThaiDate(localDate)} — ยังไม่มีรายการ`;

  const expenses = summary.rows.filter((row) => row.type === "expense");
  const incomes = summary.rows.filter((row) => row.type === "income");
  const lines = [`📊 ${formatThaiDate(localDate)}`];

  if (expenses.length > 0) {
    lines.push(`💸 จ่าย ${money(summary.expense)}฿`);
    lines.push(...expenses.map((row) => `   · ${row.label || "(ไม่มีชื่อ)"} ${money(row.amount)}`));
  }
  if (incomes.length > 0) {
    lines.push(`💰 รับ ${money(summary.income)}฿`);
    lines.push(...incomes.map((row) => `   · ${row.label || "(ไม่มีชื่อ)"} ${money(row.amount)}`));
  }
  lines.push(`คงเหลือสุทธิ ${money(summary.net)}฿`);
  return lines.join("\n");
}

const CATEGORY_TH = {
  food: "อาหาร", transport: "เดินทาง", utilities: "ค่าน้ำค่าไฟ",
  housing: "ที่พัก", health: "สุขภาพ", shopping: "ช้อปปิ้ง", salary: "เงินเดือน",
};

export function monthSummary(summary, month) {
  if (summary.count === 0) return `📊 ${formatThaiMonth(month)} — ยังไม่มีรายการ`;

  const lines = [
    `📊 ${formatThaiMonth(month)}`,
    `💰 รับ ${money(summary.income)}฿`,
    `💸 จ่าย ${money(summary.expense)}฿`,
    `คงเหลือสุทธิ ${money(summary.net)}฿`,
  ];
  if (summary.topCategories.length > 0) {
    lines.push("", "หมวดที่จ่ายมากสุด:");
    lines.push(
      ...summary.topCategories.map(
        ([category, total]) => `   · ${CATEGORY_TH[category] ?? category} ${money(total)}฿`,
      ),
    );
  }
  return lines.join("\n");
}

export function unsupported(feature) {
  if (feature === "calorie") {
    return [
      "ตอนนี้ยังบันทึกได้แค่รายรับ-รายจ่ายครับ 🙏",
      "การนับแคลอรี่กำลังจะตามมาในรอบถัดไป",
    ].join("\n");
  }
  return [
    "ข้อความนี้ดูเหมือนเป็นการนัดหมาย/ตั้งเตือน ซึ่งยังไม่รองรับครับ 🙏",
    "ตอนนี้บันทึกได้เฉพาะรายรับ-รายจ่าย เช่น `กาแฟ 120 บาท`",
  ].join("\n");
}

export function unparsed() {
  return [
    "ไม่เจอจำนวนเงินในข้อความครับ 🤔",
    "ลองพิมพ์แบบนี้: `ข้าวเช้า 50` หรือ `จ่ายค่าไฟ 1200 บาท`",
    "พิมพ์ `ช่วย` เพื่อดูวิธีใช้ทั้งหมด",
  ].join("\n");
}

export function help() {
  return [
    "📝 วิธีใช้ — พิมพ์สั้น ๆ ก็พอ",
    "",
    "บันทึกรายจ่าย",
    "   ข้าวเช้า 50",
    "   กาแฟ 120 บาท",
    "   จ่ายค่าไฟ 1,200",
    "   เมื่อวานกินหมูกระทะ 350 บาท",
    "   ค่าไฟ 1200 บาท กับค่าน้ำ 300 บาท   (บันทึกทีเดียว 2 รายการ)",
    "",
    "บันทึกรายรับ",
    "   ได้เงินเดือน 30000",
    "   +5000 ขายของ",
    "",
    "ดูยอด",
    "   สรุป          — วันนี้",
    "   สรุปเดือน     — เดือนนี้",
    "",
    "แก้ไข",
    "   ลบ            — ลบรายการล่าสุด",
    "   ลบ 3          — ลบรายการที่ 3 นับจากล่าสุด",
    "   แก้ 1500      — แก้จำนวนเงินของรายการล่าสุด",
    "",
    "ยังไม่รองรับ: นับแคลอรี่ และ to-do/แจ้งเตือน (กำลังทำรอบถัดไป)",
  ].join("\n");
}
