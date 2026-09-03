import { chromium } from 'playwright';
let pass=0, fail=0;
const ok=(c,m)=>{ if(c){pass++;console.log("  ✓ "+m);} else {fail++;console.log("  ✗ "+m);} };
const B = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
const ctx = await B.newContext({viewport:{width:390,height:844}, reducedMotion:'reduce'});
const p = await ctx.newPage();
p.on("pageerror", e => { fail++; console.log("  ✗ JS error: "+e.message); });
await p.addInitScript(s=>localStorage.setItem("tcas70.v1",JSON.stringify(s)),
  {app:"tcas70",seenIntro:true,settings:{},scores:{},topics:{},q:{},tests:{},days:{},links:{},log:{},runs:[],doneLegacy:{}});
await p.goto('http://localhost:8765/',{waitUntil:'networkidle'});
await p.waitForTimeout(500);

// ── แผงสนามสอบมีจริง
await p.evaluate(()=>go("tests")); await p.waitForTimeout(400);
ok(await p.evaluate(()=>!!document.body.textContent.includes("สนามสอบของฉัน")), "มีแผง 'สนามสอบของฉัน' ในแท็บตารางสอบ");
// ตรวจ *เนื้อหา* ของคำเตือน ไม่ใช่ถ้อยคำ — คำเตือนต้องบอกทางที่ข้อมูลออกจากเครื่องได้จริง
const warn = await p.evaluate(()=>document.body.textContent);
ok(warn.includes("ไม่ส่งข้อมูลนี้ออกไปไหนเอง"), "บอกว่าแอปไม่ส่งข้อมูลเอง");
ok(warn.includes(".ics") && warn.includes("เลขที่นั่งสอบ"), "เตือนว่าไฟล์ปฏิทินมีเลขที่นั่งสอบ");
ok(warn.includes(".json"), "เตือนว่าไฟล์สำรองมีข้อมูลนี้");
ok(warn.includes("สำรองอัตโนมัติ"), "เตือนว่าสำรองอัตโนมัติเขียนทับเองทุกครั้ง");

// ── ตัวแกะข้อความ
const parsed = await p.evaluate(()=>parseVenueText(
  "ผลการสมัครสอบ TCAS70\nเลขที่นั่งสอบ: 6812345\nสนามสอบ: โรงเรียนสวนกุหลาบวิทยาลัย\nห้องสอบ: อาคาร 3 ห้อง 402\n"));
ok(parsed.seat==="6812345", `แกะเลขที่นั่งสอบได้ (${parsed.seat})`);
ok(parsed.place.includes("สวนกุหลาบ"), `แกะสนามสอบได้ (${parsed.place})`);
ok(parsed.room.includes("402"), `แกะห้องสอบได้ (${parsed.room})`);

// ── บันทึกแล้วอยู่ใน localStorage เท่านั้น
await p.evaluate(()=>{ saveVenue("bio",{seat:"6812345",place:"ร.ร.สวนกุหลาบวิทยาลัย",room:"อาคาร 3 ห้อง 402"}); render(); });
await p.waitForTimeout(300);
const st = await p.evaluate(()=>JSON.parse(localStorage.getItem("tcas70.v1")));
ok(st.venues && st.venues.bio && st.venues.bio.seat==="6812345", "บันทึกลง localStorage แล้ว");
ok(await p.evaluate(()=>document.body.textContent.includes("6812345")), "ขึ้นในตารางสอบจริง");

// ── ไม่มีการส่งออกนอกเครื่อง
const reqs=[];
p.on("request", r => { if (!r.url().startsWith("http://localhost:8765")) reqs.push(r.url()); });
await p.evaluate(()=>{ saveVenue("chem",{seat:"9999999"}); render(); go("progress"); go("tests"); });
await p.waitForTimeout(800);
ok(reqs.length===0, `ไม่มี request ออกนอกเครื่องเลย (${reqs.length})`);

// ── ไฟล์ปฏิทินมี LOCATION
// ต้องคลี่บรรทัดที่ถูกพับตาม RFC 5545 ก่อน ไม่งั้นข้อความไทยจะขาดกลางคำ
const raw = await p.evaluate(()=>buildICS(30,19,{}));
const ics = raw.replace(/\r\n[ \t]/g, "");
ok(/LOCATION:.*สวนกุหลาบ/.test(ics), "ไฟล์ .ics มีบรรทัด LOCATION พร้อมสนามสอบ");
ok(!/LOCATION:.*ห้อง อาคาร/.test(ics), "ไม่มีคำว่า 'ห้อง' ซ้ำซ้อนใน LOCATION");
ok(/เลขที่นั่งสอบ 6812345/.test(ics), "ไฟล์ .ics มีเลขที่นั่งสอบใน DESCRIPTION");
const longLines = raw.split("\r\n").filter(l => new TextEncoder().encode(l).length > 75);
ok(longLines.length===0, `ไม่มีบรรทัดยาวเกิน 75 ออกเตต (${longLines.length})`);

// ── ไฟล์สำรอง/กู้คืน พาไปด้วย
const round = await p.evaluate(()=>{
  const backup = JSON.stringify(backupPayload());
  const clean = sanitizeBackup(JSON.parse(backup));
  return clean && clean.venues && clean.venues.bio ? clean.venues.bio.place : null;
});
ok(round && round.includes("สวนกุหลาบ"), `ไฟล์สำรองเก็บสนามสอบไว้ด้วย (${round})`);

// ── ล้างได้
await p.evaluate(()=>{ delete S.venues.bio; Store.save(); render(); });
await p.waitForTimeout(200);
ok(!(await p.evaluate(()=>JSON.parse(localStorage.getItem("tcas70.v1")).venues.bio)), "ล้างข้อมูลรายวิชาได้");

console.log(`\nรวม ${pass} ผ่าน / ${fail} ไม่ผ่าน`);
await B.close();
process.exit(fail?1:0);
