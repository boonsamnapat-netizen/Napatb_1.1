/* หา Chromium ที่ติดมากับ image — ห้ามฮาร์ดโค้ดเลขเวอร์ชัน
   เลข build กับชื่อโฟลเดอร์เปลี่ยนเองเวลา image อัปเดต (เคยเป็น
   chromium-1194/chrome-linux เปลี่ยนเป็น chromium-1243/chrome-linux64)
   และ playwright ที่ npm ลงใหม่มักมองหา build คนละตัวกับที่ image มี
   จึงต้องส่ง executablePath ให้มันตรง ๆ และห้ามรัน `playwright install` */
import { readdirSync, existsSync } from "node:fs";
import { join } from "node:path";

const ROOT = process.env.PLAYWRIGHT_BROWSERS_PATH || "/opt/pw-browsers";

export function chromePath() {
  if (process.env.CHROME_PATH && existsSync(process.env.CHROME_PATH))
    return process.env.CHROME_PATH;
  const dirs = readdirSync(ROOT)
    .filter(d => /^chromium-\d+$/.test(d))
    .sort((a, b) => Number(b.split("-")[1]) - Number(a.split("-")[1]));
  for (const d of dirs)
    for (const sub of ["chrome-linux64", "chrome-linux"]) {
      const p = join(ROOT, d, sub, "chrome");
      if (existsSync(p)) return p;
    }
  throw new Error(
    "หา Chromium ใน " + ROOT + " ไม่เจอ — ดูว่ามีโฟลเดอร์ chromium-* อยู่ไหม " +
    "หรือตั้ง CHROME_PATH ชี้ไปที่ binary เอง");
}
