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

/** 1,240 / 2,000 kcal — or just the figure when no goal is set. */
function kcalAgainstGoal(netKcal, goal) {
  const shown = `${money(netKcal)} kcal`;
  if (!goal) return shown;
  const left = goal - netKcal;
  const verdict = left >= 0 ? `เหลืออีก ${money(left)}` : `เกินมา ${money(-left)}`;
  return `${money(netKcal)} / ${money(goal)} kcal · ${verdict}`;
}

function calorieLine(entry) {
  if (entry.direction === "burn") {
    const duration = entry.durationMin ? ` ${money(entry.durationMin)} นาที` : "";
    return `🏃 ${entry.label || "ออกกำลังกาย"}${duration} −${money(entry.kcal)} kcal`;
  }
  return `🍚 ${entry.label || "(ไม่มีชื่อ)"} ${money(entry.kcal)} kcal`;
}

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
export function savedEntries(entries, totals, totalsDate, todayDate, options = {}) {
  const { goal = null, learned = [] } = options;

  const lines = entries.map((entry) => {
    const when = entry.localDate === todayDate ? "" : ` (${formatThaiDate(entry.localDate)})`;
    if (entry.type === "calorie") {
      const source = entry.fromMemory ? " · ใช้ค่าที่จำไว้" : "";
      return `${calorieLine(entry)}${when}${source}`;
    }
    const sign = entry.type === "income" ? "+" : "";
    const label = entry.label || "(ไม่มีชื่อ)";
    return `${ICON[entry.type]} ${label} ${sign}${money(entry.amount)}฿${when}`;
  });

  const dayName = totalsDate === todayDate ? "วันนี้" : formatThaiDate(totalsDate);
  // Only total the units this batch actually touched — a coffee should not drag
  // an unrelated calorie figure into the reply.
  if (entries.some((entry) => entry.type !== "calorie")) {
    lines.push(`— ${dayName} จ่าย ${money(totals.expense)}฿ · รับ ${money(totals.income)}฿`);
  }
  if (entries.some((entry) => entry.type === "calorie")) {
    lines.push(`— ${dayName} ${kcalAgainstGoal(totals.netKcal, goal)}`);
  }

  // Only nudge when the reading really was a coin flip.
  if (entries.some((entry) => entry.needsConfirm)) {
    lines.push("↳ ไม่ใช่รายจ่าย? พิมพ์ `ค` เพื่อบันทึกเป็นแคลแทน");
  }
  for (const label of learned) {
    lines.push(`↳ จำ "${label}" ไว้แล้ว ครั้งหน้าพิมพ์แค่ \`ค ${label}\` ก็พอ`);
  }
  return lines.join("\n");
}

/** The bot has no figure for this dish and will not invent one. */
export function needFigure(label, direction) {
  if (direction === "burn") {
    return [
      `"${label}" เผาไปกี่แคลครับ? 🤔`,
      "แคลที่เผาขึ้นกับระยะเวลาและน้ำหนักตัว ผมเลยไม่เดาให้",
      `พิมพ์เลขต่อท้ายได้เลย เช่น \`${label} 30 นาที 300 แคล\``,
    ].join("\n");
  }
  return [
    `"${label}" กี่แคลครับ? 🤔`,
    "ผมไม่มีตารางแคลอรี่อาหารไทยที่เชื่อถือได้ เลยไม่เดาให้",
    `บอกครั้งเดียวพอ เช่น \`ค ${label} 250\` แล้วผมจะจำไว้ ครั้งหน้าพิมพ์แค่ \`ค ${label}\``,
  ].join("\n");
}

export function remembered(label, kcal, isUpdate) {
  const verb = isUpdate ? "แก้เป็น" : "จำไว้แล้ว";
  return `🧠 "${label}" ${verb} ${money(kcal)} kcal\nครั้งหน้าพิมพ์แค่ \`ค ${label}\` ก็พอ`;
}

export function forgotten(label, existed) {
  return existed ? `🧠 ลืม "${label}" แล้ว` : `ไม่เคยจำ "${label}" ไว้ครับ`;
}

export function memories(rows) {
  if (rows.length === 0) {
    return "ยังไม่ได้จำอะไรไว้เลยครับ\nลองพิมพ์ `จำ ข้าวมันไก่ 600`";
  }
  return [
    "🧠 ที่จำไว้:",
    ...rows.map((row) => {
      const sign = row.direction === "burn" ? "−" : "";
      return `   · ${row.name} ${sign}${money(row.kcal)} kcal`;
    }),
    "",
    "ลบทีละอันด้วย `ลืม <ชื่อ>`",
  ].join("\n");
}

export function goalSet(kcal) {
  return `🎯 ตั้งเป้าไว้ ${money(kcal)} kcal ต่อวัน`;
}

export function goalShow(kcal) {
  if (!kcal) return "ยังไม่ได้ตั้งเป้าครับ — พิมพ์ `เป้า 2000` เพื่อตั้ง";
  return `🎯 เป้าตอนนี้ ${money(kcal)} kcal ต่อวัน`;
}

/** The figure and unit a row carries, whichever kind it is. */
function figureOf(row) {
  if (row.type === "calorie") {
    return { value: row.kcal, unit: " kcal", sign: row.direction === "burn" ? "−" : "" };
  }
  return { value: row.amount, unit: "฿", sign: row.type === "income" ? "+" : "" };
}

export function deleted(row) {
  const { value, unit, sign } = figureOf(row);
  return `🗑 ลบแล้ว: ${row.label || row.raw} ${sign}${money(value)}${unit}`;
}

export function amended(row, oldValue) {
  const { value, unit } = figureOf(row);
  return `✏️ แก้แล้ว: ${row.label || row.raw} ${money(oldValue)}${unit} → ${money(value)}${unit}`;
}

export function nothingToDelete() {
  return "ไม่มีรายการให้ลบครับ";
}

export function daySummary(summary, localDate, goal = null) {
  if (summary.count === 0) return `📊 ${formatThaiDate(localDate)} — ยังไม่มีรายการ`;

  const expenses = summary.rows.filter((row) => row.type === "expense");
  const incomes = summary.rows.filter((row) => row.type === "income");
  const eaten = summary.calorieRows.filter((row) => row.direction !== "burn");
  const burned = summary.calorieRows.filter((row) => row.direction === "burn");
  const lines = [`📊 ${formatThaiDate(localDate)}`];

  if (expenses.length > 0) {
    lines.push(`💸 จ่าย ${money(summary.expense)}฿`);
    lines.push(...expenses.map((row) => `   · ${row.label || "(ไม่มีชื่อ)"} ${money(row.amount)}`));
  }
  if (incomes.length > 0) {
    lines.push(`💰 รับ ${money(summary.income)}฿`);
    lines.push(...incomes.map((row) => `   · ${row.label || "(ไม่มีชื่อ)"} ${money(row.amount)}`));
  }
  if (expenses.length > 0 || incomes.length > 0) {
    lines.push(`คงเหลือสุทธิ ${money(summary.net)}฿`);
  }

  if (summary.calorieRows.length > 0) {
    if (expenses.length > 0 || incomes.length > 0) lines.push("");
    lines.push(`🍚 กิน ${money(summary.intake)} kcal`);
    lines.push(...eaten.map((row) => `   · ${row.label || "(ไม่มีชื่อ)"} ${money(row.kcal)}`));
    if (burned.length > 0) {
      lines.push(`🏃 เผา ${money(summary.burn)} kcal`);
      lines.push(...burned.map((row) => `   · ${row.label || "ออกกำลังกาย"} ${money(row.kcal)}`));
    }
    lines.push(`สุทธิ ${kcalAgainstGoal(summary.netKcal, goal)}`);
  }
  return lines.join("\n");
}

const CATEGORY_TH = {
  food: "อาหาร", transport: "เดินทาง", utilities: "ค่าน้ำค่าไฟ",
  housing: "ที่พัก", health: "สุขภาพ", shopping: "ช้อปปิ้ง", salary: "เงินเดือน",
};

export function monthSummary(summary, month, calorieDays = 0, goal = null) {
  if (summary.count === 0) return `📊 ${formatThaiMonth(month)} — ยังไม่มีรายการ`;

  const lines = [`📊 ${formatThaiMonth(month)}`];

  if (summary.rows.length > 0) {
    lines.push(
      `💰 รับ ${money(summary.income)}฿`,
      `💸 จ่าย ${money(summary.expense)}฿`,
      `คงเหลือสุทธิ ${money(summary.net)}฿`,
    );
  }
  if (summary.topCategories.length > 0) {
    lines.push("", "หมวดที่จ่ายมากสุด:");
    lines.push(
      ...summary.topCategories.map(
        ([category, total]) => `   · ${CATEGORY_TH[category] ?? category} ${money(total)}฿`,
      ),
    );
  }

  if (summary.calorieRows.length > 0) {
    lines.push("");
    // Averaged over days that actually have entries, not calendar days — a
    // month with three days logged should not read as if the other 28 were zero.
    const average = calorieDays > 0 ? summary.netKcal / calorieDays : summary.netKcal;
    lines.push(`🍚 เฉลี่ย ${money(Math.round(average))} kcal/วัน (${calorieDays} วันที่บันทึก)`);
    if (goal) lines.push(`🎯 เป้า ${money(goal)} kcal/วัน`);
  }
  return lines.join("\n");
}

export function unsupported(feature) {
  return [
    "ข้อความนี้ดูเหมือนเป็นการนัดหมาย/ตั้งเตือน ซึ่งยังไม่รองรับครับ 🙏",
    "ตอนนี้บันทึกได้เฉพาะรายรับ-รายจ่าย และแคลอรี่",
  ].join("\n");
}

export function unparsed() {
  return [
    "ไม่เจอตัวเลขในข้อความครับ 🤔",
    "ลองพิมพ์แบบนี้: `ข้าวเช้า 50` · `จ่ายค่าไฟ 1200 บาท` · `ค ข้าวมันไก่ 600`",
    "พิมพ์ `ช่วย` เพื่อดูวิธีใช้ทั้งหมด",
  ].join("\n");
}

export function help() {
  return [
    "📝 วิธีใช้ — พิมพ์สั้น ๆ ก็พอ",
    "",
    "💸 รายจ่าย",
    "   ข้าวเช้า 50",
    "   กาแฟ 120 บาท",
    "   เมื่อวานกินหมูกระทะ 350 บาท",
    "   ค่าไฟ 1200 บาท กับค่าน้ำ 300 บาท   (บันทึกทีเดียว 2 รายการ)",
    "",
    "💰 รายรับ",
    "   ได้เงินเดือน 30000",
    "   +5000 ขายของ",
    "",
    "🍚 แคลอรี่",
    "   ข้าวมันไก่ 600 แคล",
    "   ค ข้าวมันไก่ 600      (ค = แคล ไม่ใช่เงิน)",
    "   ค ข้าวมันไก่          (ครั้งต่อไปไม่ต้องใส่เลข ผมจำให้)",
    "   วิ่ง 30 นาที 300 แคล   (ออกกำลังกาย = ลบออก)",
    "   หมูกระทะ 800 แคล จ่าย 350 บาท   (บันทึกทั้งแคลและเงิน)",
    "",
    "🧠 สอนให้จำ",
    "   จำ ข้าวมันไก่ 600",
    "   ลืม ข้าวมันไก่",
    "   รายการจำ",
    "   เป้า 2000            — ตั้งเป้าแคลต่อวัน",
    "",
    "📊 ดูยอด",
    "   สรุป / สรุปเดือน",
    "",
    "✏️ แก้ไข",
    "   ลบ · ลบ 3 · แก้ 1500",
    "",
    "ยังไม่รองรับ: to-do / แจ้งเตือนตามเวลา (รอบถัดไป)",
  ].join("\n");
}
