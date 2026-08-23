(function(){
"use strict";
const $ = id => document.getElementById(id);
const KEY = "tdee.v1";
const KCAL_PER_KG = 7700;          // พลังงานต่อไขมัน 1 กก.
const FLOOR = { male: 1500, female: 1200 };

/* ─────────── state ─────────── */
const S = {
  sex: "male", age: 30, ht: 172, wt: 70, bf: null, goalWt: null,
  act: 1.375, formula: "mifflin",
  goalPct: -15, proPerKg: 2.0, fatPct: 25, meals: 3,
  log: [],                      // [{d, w, k}] — ชั่งน้ำหนัก + kcal ที่กรอกมือ
  foods: [],                    // [{id, d, meal, name, qty, kcal, p, f, c, src, photo, barcode}]
  lib: [],                      // คลังอาหารส่วนตัว [{id, name, qty, kcal, p, f, c, barcode, n, last}]
  ai: { url: "", token: "" },   // ที่อยู่ Worker + รหัสแอป (เก็บในเครื่องเท่านั้น)
  theme: null
};
let fday = null;                // วันที่ที่กำลังดูอยู่ในแท็บอาหาร

function load(){
  try{
    const raw = localStorage.getItem(KEY);
    if(raw) Object.assign(S, JSON.parse(raw));
  }catch(e){/* private mode / blocked storage — carry on with defaults */}
  if(!Array.isArray(S.log)) S.log = [];
  if(!Array.isArray(S.foods)) S.foods = [];
  if(!Array.isArray(S.lib)) S.lib = [];
  if(!S.ai || typeof S.ai !== "object") S.ai = { url: "", token: "" };
}
let saveTimer = null;
function save(){
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    try{ localStorage.setItem(KEY, JSON.stringify(S)); }catch(e){}
  }, 150);
}

/* ─────────── helpers ─────────── */
const n0 = v => Math.round(v).toLocaleString("en-US");
const n1 = v => v.toFixed(1);
const num = el => { const v = parseFloat(el.value); return Number.isFinite(v) ? v : null; };
const dayNum = d => Math.round(new Date(d + "T00:00:00").getTime() / 86400000);
const todayISO = () => { const t = new Date(); t.setMinutes(t.getMinutes() - t.getTimezoneOffset()); return t.toISOString().slice(0,10); };
const thDate = d => { const p = d.split("-"); return p[2] + "/" + p[1]; };

/* ─────────── metabolism ─────────── */
function lbm(){ return S.bf != null ? S.wt * (1 - S.bf/100) : null; }

function bmrOf(f){
  const w = S.wt, h = S.ht, a = S.age;
  if(f === "katch"){ const l = lbm(); return l == null ? null : 370 + 21.6 * l; }
  if(f === "harris") return S.sex === "male"
      ? 88.362 + 13.397*w + 4.799*h - 5.677*a
      : 447.593 +  9.247*w + 3.098*h - 4.330*a;
  return 10*w + 6.25*h - 5*a + (S.sex === "male" ? 5 : -161);   // Mifflin-St Jeor
}
function bmr(){ return bmrOf(S.formula) ?? bmrOf("mifflin"); }
function tdee(){ return bmr() * S.act; }

const GOALS = [
  { pct:  10, label: "เพิ่มกล้ามแบบลีน", note: "ส่วนเกินพอดี ไขมันขึ้นน้อย" },
  { pct:   0, label: "รักษาน้ำหนัก",     note: "กินเท่าที่เผา" },
  { pct: -10, label: "ลดช้า / รีคอมป์",  note: "เก็บกล้ามได้ดีที่สุด หิวน้อย" },
  { pct: -15, label: "ลดปกติ",           note: "สมดุลระหว่างเร็วกับยั่งยืน", rec: true },
  { pct: -20, label: "ลดเร็ว",           note: "ต้องเวทเทรน + โปรตีนสูง ไม่งั้นเสียกล้าม" },
  { pct: -25, label: "ลดเร่ง",           note: "หิวหนัก แรงตก ทำได้ไม่นาน", warn: true }
];
const goalOf = p => GOALS.find(g => g.pct === p) || GOALS[3];

function targetKcal(pct){ return tdee() * (1 + pct/100); }
function kgPerWeek(pct){ return (tdee() * pct/100) * 7 / KCAL_PER_KG; }
function floorKcal(){ return FLOOR[S.sex]; }

/* ─────────── macros ─────────── */
function macros(){
  const kcal = targetKcal(S.goalPct);
  const proG = S.wt * S.proPerKg;
  const proK = proG * 4;
  let fatG = (kcal * S.fatPct/100) / 9;
  const fatMin = S.wt * 0.6;                    // ขั้นต่ำเพื่อฮอร์โมน
  const fatClamped = fatG < fatMin;
  if(fatClamped) fatG = fatMin;
  const fatK = fatG * 9;
  let carbK = kcal - proK - fatK;
  const short = carbK < 0;
  if(short) carbK = 0;
  return { kcal, proG, proK, fatG, fatK, carbG: carbK/4, carbK, fatClamped, short };
}

/* ─────────── render: readout panel ─────────── */
function renderLabel(){
  const b = bmr(), t = tdee(), m = macros();
  $("o-bmr").textContent  = n0(b) + " kcal";
  $("o-mult").textContent = "× " + S.act;
  $("o-tdee").textContent = n0(t);

  const g = goalOf(S.goalPct);
  const kw = kgPerWeek(S.goalPct);
  $("o-goal-label").textContent = "เป้าหมาย — " + g.label;
  $("o-target").textContent = n0(m.kcal);
  const delta = m.kcal - t;
  $("o-target-why").textContent = S.goalPct === 0
    ? "เท่ากับที่เผา น้ำหนักนิ่ง"
    : (delta < 0 ? "ขาดดุล " : "เกินดุล ") + n0(Math.abs(delta)) + " kcal/วัน · ประมาณ "
      + (kw > 0 ? "+" : "") + n1(kw) + " กก./สัปดาห์";

  // stacked macro bar — direct-labelled, 2px gaps
  const parts = [
    { g: m.proG,  k: m.proK,  c: "var(--m-pro)",  t: "โปรตีน" },
    { g: m.fatG,  k: m.fatK,  c: "var(--m-fat)",  t: "ไขมัน"  },
    { g: m.carbG, k: m.carbK, c: "var(--m-carb)", t: "คาร์บ"  }
  ];
  const tot = m.proK + m.fatK + m.carbK || 1;
  $("macbar").innerHTML = parts.map(p => {
    const pc = p.k/tot*100;
    return '<span style="flex:' + pc.toFixed(2) + ' 1 0%;background:' + p.c + '">'
         + (pc > 11 ? Math.round(pc) + "%" : "") + "</span>";
  }).join("");
  $("macrotable").innerHTML = parts.map(p =>
      '<tr><td><span class="swatch" style="background:' + p.c + '"></span>' + p.t + "</td>"
    + '<td class="n">' + n0(p.g) + " ก.</td>"
    + '<td class="p">' + n0(p.k) + "</td></tr>"
  ).join("") + '<tr><td style="color:var(--ink-3)">รวมพลังงาน</td><td class="n"></td><td class="p">' + n0(tot) + "</td></tr>";

  const perMeal = m.proG / S.meals;
  const perMealMin = S.wt * 0.25;
  $("o-permeal").textContent = n0(perMeal) + " ก. × " + S.meals;
  $("o-water").textContent   = n1(S.wt * 35 / 1000) + " ล.";

  const bmi = S.wt / Math.pow(S.ht/100, 2);
  $("o-bmi").textContent = n1(bmi);
  const lo = 18.5 * Math.pow(S.ht/100,2), hi = 22.9 * Math.pow(S.ht/100,2);
  const cat = bmi < 18.5 ? "ผอม" : bmi < 23 ? "ปกติ" : bmi < 25 ? "ท้วม" : bmi < 30 ? "อ้วนระดับ 1" : "อ้วนระดับ 2";
  $("o-bmi-note").textContent = cat + " · ช่วงปกติสำหรับส่วนสูงนี้ " + n1(lo) + "–" + n1(hi) + " กก. (เกณฑ์เอเชีย)";

  const l = lbm();
  $("o-lbm").textContent = l == null ? "—" : n1(l) + " กก.";
  $("bf-hint").textContent = l == null
    ? "ไม่รู้ % ไขมันก็ใช้ได้ปกติ — ถ้าใส่มา จะปลดล็อกสูตร Katch-McArdle ที่แม่นกว่าและคิดมวลไร้ไขมันให้"
    : "มวลไร้ไขมัน " + n1(l) + " กก. · มวลไขมัน " + n1(S.wt - l) + " กก.";

  // macro sanity notes
  const mn = $("macro-note");
  let msg = [], cls = "note";
  if(m.short){ msg.push("<b>แคลไม่พอ</b> โปรตีนกับไขมันรวมกันเกินเป้าแล้ว ลดโปรตีน/ไขมันลง หรือเพิ่มแคลเป้าหมาย"); cls = "note bad"; }
  else if(m.carbG < 50){ msg.push("คาร์บเหลือแค่ " + n0(m.carbG) + " ก. — ต่ำมาก แรงซ้อมจะตก ลองลดไขมันลงหน่อย"); cls = "note warn"; }
  if(m.fatClamped) msg.push("ดันไขมันขึ้นเป็นขั้นต่ำ " + n0(S.wt*0.6) + " ก. (0.6 ก./กก.) แล้ว ต่ำกว่านี้ฮอร์โมนจะรวน");
  if(perMeal < perMealMin) msg.push("โปรตีนต่อมื้อ " + n0(perMeal) + " ก. ต่ำกว่าที่กระตุ้นการสร้างกล้ามได้เต็มที่ (~" + n0(perMealMin) + " ก.) — ลดจำนวนมื้อลงหรือเพิ่มโปรตีน");
  if(!msg.length && S.goalPct < 0) msg.push("โปรตีน " + S.proPerKg.toFixed(1) + " ก./กก. อยู่ในช่วง 1.6–2.2 ที่งานวิจัยใช้รักษากล้ามระหว่างลดไขมัน");
  mn.className = cls;
  mn.innerHTML = msg.join(" · ") || "&nbsp;";
}

/* ─────────── render: goal table ─────────── */
function renderGoals(){
  const t = tdee(), fl = floorKcal();
  $("goalbody").innerHTML = GOALS.map(g => {
    const k = targetKcal(g.pct), kw = kgPerWeek(g.pct);
    const below = k < fl;
    let tag = "";
    if(g.rec)  tag = ' <span class="pill rec">แนะนำ</span>';
    if(below)  tag = ' <span class="pill bad">ต่ำเกินไป</span>';
    else if(g.warn) tag = ' <span class="pill warn">ระวัง</span>';
    return '<tr data-pct="' + g.pct + '" data-on="' + (g.pct === S.goalPct ? 1 : 0) + '">'
      + '<td class="name"><span class="gname"><span class="tick"></span><b>' + g.label + "</b>" + tag + "</span>"
      + '<span class="gnote">' + g.note + "</span></td>"
      + '<td class="c">' + (g.pct > 0 ? "+" : "") + g.pct + "%</td>"
      + '<td class="c">' + n0(k) + "</td>"
      + '<td class="c ' + (kw < 0 ? "neg" : kw > 0 ? "pos" : "") + '">' + (kw > 0 ? "+" : "") + n1(kw) + "</td></tr>";
  }).join("");

  const g = goalOf(S.goalPct), k = targetKcal(S.goalPct), gn = $("goal-note");
  if(k < fl){
    gn.className = "note bad";
    gn.innerHTML = "<b>" + n0(k) + " kcal ต่ำกว่าขั้นต่ำ " + n0(fl) + " kcal</b> ที่ควรกินต่อวัน — กินต่ำขนาดนี้นาน ๆ เสี่ยงขาดสารอาหาร แรงตก และเสียกล้าม เลือกระดับที่ลดช้ากว่านี้ แล้วเพิ่มการเดิน/ซ้อมแทน";
  } else if(g.warn){
    gn.className = "note warn";
    gn.innerHTML = "งานวิจัยส่วนใหญ่แนะนำขาดดุล <b>10–20%</b> ระดับนี้เกินมา — ถ้าจะใช้จริง อย่าใช้เกิน 6–8 สัปดาห์แล้วกลับมากินระดับรักษาสักพัก";
  } else {
    gn.className = "note good";
    gn.innerHTML = "อยู่ในช่วงที่แนะนำ · ลดไขมันได้โดยเก็บกล้ามไว้ ถ้าโปรตีนถึงและมีเวทเทรน";
  }

  const eta = $("eta-note"), kw = kgPerWeek(S.goalPct);
  if(S.goalWt != null && Math.abs(S.wt - S.goalWt) > 0.2 && kw !== 0 && (S.goalWt - S.wt) / kw > 0){
    const weeks = (S.goalWt - S.wt) / kw;
    const d = new Date(); d.setDate(d.getDate() + Math.round(weeks * 7));
    eta.hidden = false;
    eta.className = "note";
    eta.innerHTML = "จาก <b>" + n1(S.wt) + " → " + n1(S.goalWt) + " กก.</b> ที่อัตรานี้ใช้เวลาราว <b>"
      + Math.round(weeks) + " สัปดาห์</b> ถึงประมาณ " + d.toLocaleDateString("th-TH", {day:"numeric", month:"long", year:"numeric"})
      + " — ของจริงจะช้ากว่านี้นิดหน่อยเพราะ TDEE ลดตามน้ำหนักที่ลดลง";
  } else eta.hidden = true;
}

/* ─────────── render: formula comparison ─────────── */
function renderFormulas(){
  const rows = [
    ["mifflin", "Mifflin-St Jeor"],
    ["katch",   "Katch-McArdle"],
    ["harris",  "Harris-Benedict"]
  ];
  $("formulatable").innerHTML = rows.map(([k, name]) => {
    const b = bmrOf(k);
    const on = k === S.formula;
    return "<tr><td" + (on ? ' style="font-weight:600"' : "") + ">" + name
      + (on ? ' <span class="pill rec">ใช้อยู่</span>' : "") + "</td>"
      + '<td class="n">' + (b == null ? "ต้องใส่ % ไขมัน" : n0(b) + " kcal") + "</td>"
      + '<td class="p">' + (b == null ? "—" : n0(b * S.act)) + "</td></tr>";
  }).join("") + '<tr><td style="color:var(--ink-3);font-size:12px">BMR · TDEE (kcal)</td><td></td><td></td></tr>';
}

/* ─────────── tracker: local-linear trend + back-calculated TDEE ───────────
   ปรับเรียบด้วยการฟิตเส้นตรงบนข้อมูลดิบ 21 วันย้อนหลังของแต่ละจุด
   (ไม่ใช้ค่าเฉลี่ยเคลื่อนที่ เพราะมันหน่วง ทำให้เทรนด์ตื้นกว่าจริงและ TDEE เพี้ยนต่ำ) */
const WINDOW = 21;      // วันที่ใช้ฟิตเส้นเทรนด์

function fit(rows){                       // least squares: น้ำหนัก ~ วัน
  const n = rows.length;
  if(n < 2) return null;
  const mx = rows.reduce((s,r) => s + r.x, 0) / n;
  const my = rows.reduce((s,r) => s + r.w, 0) / n;
  let sxy = 0, sxx = 0;
  rows.forEach(r => { sxy += (r.x - mx) * (r.w - my); sxx += (r.x - mx) * (r.x - mx); });
  if(sxx <= 0) return null;
  const slope = sxy / sxx;
  return { slope, at: x => my + slope * (x - mx) };
}

/* kcal ที่กินในวันนั้น — ถ้าบันทึกอาหารเป็นรายการไว้ ให้บวกจากรายการ
   ไม่งั้นค่อยใช้เลขรวมที่กรอกมือในแท็บติดตามจริง */
function foodKcal(d){
  const f = S.foods.filter(x => x.d === d);
  return f.length ? f.reduce((s, x) => s + (x.kcal || 0), 0) : null;
}
function foodMacros(d){
  return S.foods.filter(x => x.d === d).reduce(
    (a, x) => ({ p: a.p + (x.p||0), f: a.f + (x.f||0), c: a.c + (x.c||0) }), { p:0, f:0, c:0 });
}
function intakeFor(d){
  const fk = foodKcal(d);
  if(fk != null) return fk;
  const r = S.log.find(x => x.d === d);
  return r && r.k != null ? r.k : null;
}
function intakeDays(){
  const set = new Set([...S.log.filter(r => r.k != null).map(r => r.d), ...S.foods.map(f => f.d)]);
  return [...set].map(d => ({ d, k: intakeFor(d) })).filter(r => r.k != null);
}
function allDates(){
  return [...new Set([...S.log.map(r => r.d), ...S.foods.map(f => f.d)])];
}

function series(){
  const rows = S.log.filter(r => r.w != null)
    .map(r => ({ d: r.d, x: dayNum(r.d), w: r.w }))
    .sort((a,b) => a.x - b.x);
  // ค่าเทรนด์ของแต่ละจุด = เส้นตรงที่ฟิตจาก 21 วันก่อนหน้าจุดนั้น (ไม่มี lag ที่ปลายเส้น)
  return rows.map((r,i) => {
    const win = rows.slice(0, i+1).filter(q => q.x > r.x - WINDOW);
    const f = win.length >= 3 && (win[win.length-1].x - win[0].x) >= 5 ? fit(win) : null;
    const run = win.reduce((s,q) => s + q.w, 0) / win.length;
    return { d: r.d, x: r.x, w: r.w, t: f ? f.at(r.x) : run };
  });
}

function adaptive(){
  const sm = series();
  if(!sm.length) return { sm: [], ok: false, days: 0 };
  const last = sm[sm.length - 1].x;
  const win = sm.filter(r => r.x > last - WINDOW);
  const span = win.length > 1 ? win[win.length-1].x - win[0].x + 1 : 1;

  const f = (win.length >= 3 && span >= 7) ? fit(win) : null;
  const slope = f ? f.slope : null;                       // กก./วัน

  const eats = intakeDays().filter(r => dayNum(r.d) > last - WINDOW);
  const meanK = eats.length ? eats.reduce((s,r) => s + r.k, 0) / eats.length : null;

  const ok = slope != null && meanK != null && eats.length >= 10 && win.length >= 10 && span >= 14;
  return {
    sm, win, ok, span,
    days: Math.min(eats.length, win.length),
    slope, meanK, eats: eats.length,
    trendW: f ? f.at(last) : sm[sm.length-1].t,
    tdee: (slope != null && meanK != null) ? meanK - slope * KCAL_PER_KG : null
  };
}

function renderTrack(){
  const a = adaptive();
  const set = (id, v, s) => { $(id).textContent = v; if(s != null) $(id + "-s").textContent = s; };

  if(a.tdee != null){
    set("a-tdee", n0(a.tdee), a.ok ? "kcal/วัน · เชื่อถือได้" : "kcal/วัน · ยังต้องเก็บข้อมูลอีก");
    $("a-tdee").innerHTML = n0(a.tdee) + ' <small class="u">kcal</small>';
  } else set("a-tdee", "—", "ต้องมีน้ำหนัก + kcal อย่างน้อย 10 วัน");

  set("a-trend", a.sm.length ? n1(a.trendW) + " " : "—", a.sm.length ? "กก. · ล่าสุด " + thDate(a.sm[a.sm.length-1].d) : "ยังไม่มีข้อมูล");
  if(a.sm.length) $("a-trend").innerHTML = n1(a.trendW) + ' <small class="u">กก.</small>';

  if(a.slope != null){
    const kw = a.slope * 7;
    $("a-rate").innerHTML = (kw > 0 ? "+" : "") + n1(kw) + ' <small class="u">กก./สัปดาห์</small>';
    $("a-rate").style.color = kw < -0.02 ? "var(--good)" : kw > 0.02 ? "var(--warn)" : "var(--ink)";
    $("a-rate-s").textContent = "จาก " + a.win.length + " ครั้งที่ชั่งใน " + a.span + " วัน";
  } else { $("a-rate").textContent = "—"; $("a-rate-s").textContent = "ต้องชั่งอย่างน้อย 3 ครั้ง ห่างกัน 7 วัน"; }

  set("a-intake", a.meanK != null ? n0(a.meanK) : "—", a.meanK != null ? "kcal/วัน · เฉลี่ย " + a.eats + " วัน" : "kcal/วัน");

  const v = $("a-verdict");
  if(a.tdee == null){
    const need = Math.max(0, 10 - a.days);
    v.className = "note";
    v.innerHTML = "ชั่งน้ำหนักตอนเช้าหลังเข้าห้องน้ำก่อนกินอะไร แล้วบันทึกแคลที่กินทั้งวัน — อีก <b>" + need + " วัน</b> ระบบจะเริ่มบอก TDEE จริงของคุณได้";
  } else {
    const est = tdee(), diff = a.tdee - est, pct = diff / est * 100;
    const newTarget = a.tdee * (1 + S.goalPct/100);
    let head;
    if(!a.ok) head = "<b>ตัวเลขเบื้องต้น</b> (ข้อมูลยังไม่ครบ 14 วัน อาจแกว่ง) — ";
    else if(Math.abs(pct) < 5) head = "<b>สูตรตรงกับตัวจริง</b> ต่างกันแค่ " + n1(Math.abs(pct)) + "% — ";
    else if(diff < 0) head = "<b>คุณเผาน้อยกว่าที่สูตรบอก " + n0(-diff) + " kcal</b> (" + n1(Math.abs(pct)) + "%) — มักแปลว่าประเมินระดับกิจกรรมสูงไป หรือแคลที่บันทึกต่ำกว่าจริง — ";
    else head = "<b>คุณเผามากกว่าที่สูตรบอก " + n0(diff) + " kcal</b> (" + n1(pct) + "%) — ";
    v.className = a.ok ? "note good" : "note warn";
    v.innerHTML = head + "ถ้าจะเดินเป้าหมาย <b>" + goalOf(S.goalPct).label + " (" + S.goalPct + "%)</b> ต่อจากนี้ ให้ยึด <b>" + n0(newTarget) + " kcal/วัน</b> แทนเลข " + n0(targetKcal(S.goalPct)) + " จากสูตร";
  }

  // log table
  const rows = allDates().sort().reverse().map(d => {
    const r = S.log.find(x => x.d === d) || {};
    return { d, w: r.w != null ? r.w : null, k: intakeFor(d), auto: foodKcal(d) != null };
  });
  $("logcount").textContent = rows.length ? "(" + rows.length + ")" : "";
  $("log-hint").textContent = rows.length ? rows.length + " วัน" : "";
  $("logbody").innerHTML = rows.length
    ? rows.map(r => '<tr><td>' + thDate(r.d) + "</td><td>" + (r.w != null ? n1(r.w) : "—")
        + "</td><td>" + (r.k != null ? n0(r.k) : "—")
        + (r.auto ? '<span class="srcpill">จากรายการ</span>' : "")
        + '</td><td><button class="del" type="button" data-d="' + r.d + '" aria-label="ลบ ' + r.d + '">×</button></td></tr>').join("")
    : '<tr class="empty"><td colspan="4">ยังไม่มีข้อมูล — เริ่มจากชั่งน้ำหนักพรุ่งนี้เช้า</td></tr>';

  drawChart(a);
}

/* ─────────── chart ─────────── */
const cv = $("chart"), tip = $("tip");
let pts = [];
function css(v){ return getComputedStyle(document.body).getPropertyValue(v).trim(); }

function drawChart(a){
  const dpr = window.devicePixelRatio || 1;
  const W = cv.clientWidth, H = cv.clientHeight;
  if(!W || !H) return;
  cv.width = W * dpr; cv.height = H * dpr;
  const c = cv.getContext("2d");
  c.setTransform(dpr, 0, 0, dpr, 0, 0);
  c.clearRect(0, 0, W, H);
  pts = [];

  const sm = a.sm;
  const inkMuted = css("--ink-3"), grid = css("--grid"), accent = css("--accent"), dot = css("--dot"), surface = css("--card");
  const fBody = css("--f-body"), fData = css("--f-data");

  if(sm.length < 2){
    c.fillStyle = inkMuted;
    c.font = "13px " + fBody;
    c.textAlign = "center";
    c.fillText("บันทึกน้ำหนักอย่างน้อย 2 วันเพื่อดูกราฟ", W/2, H/2);
    return;
  }

  const padL = 42, padR = 14, padT = 14, padB = 24;
  const xs = sm.map(p => p.x), ws = sm.flatMap(p => [p.w, p.t]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  let y0 = Math.min(...ws), y1 = Math.max(...ws);
  const pad = Math.max((y1 - y0) * 0.18, 0.5);
  y0 -= pad; y1 += pad;
  const X = v => padL + (v - x0) / Math.max(x1 - x0, 1) * (W - padL - padR);
  const Y = v => padT + (y1 - v) / (y1 - y0) * (H - padT - padB);

  // recessive grid + y labels
  c.strokeStyle = grid; c.lineWidth = 1;
  c.fillStyle = inkMuted;
  c.font = "11px " + fData;
  c.textAlign = "right"; c.textBaseline = "middle";
  for(let i = 0; i <= 3; i++){
    const v = y0 + (y1 - y0) * i / 3, y = Math.round(Y(v)) + 0.5;
    c.beginPath(); c.moveTo(padL, y); c.lineTo(W - padR, y); c.stroke();
    c.fillText(v.toFixed(1), padL - 8, y);
  }
  // x labels: first & last
  c.textAlign = "left"; c.textBaseline = "top";
  c.font = "11px " + fBody;
  c.fillText(thDate(sm[0].d), padL, H - padB + 6);
  c.textAlign = "right";
  c.fillText(thDate(sm[sm.length-1].d), W - padR, H - padB + 6);

  // raw weigh-ins — recessive dots with a surface ring
  sm.forEach(p => {
    const px = X(p.x), py = Y(p.w);
    pts.push({ px, py, p });
    c.beginPath(); c.arc(px, py, 4, 0, Math.PI*2);
    c.fillStyle = dot; c.fill();
    c.lineWidth = 2; c.strokeStyle = surface; c.stroke();
  });

  // trend line — 2px, the emphasised mark
  c.beginPath();
  sm.forEach((p, i) => { const px = X(p.x), py = Y(p.t); i ? c.lineTo(px, py) : c.moveTo(px, py); });
  c.strokeStyle = accent; c.lineWidth = 2; c.lineJoin = "round"; c.lineCap = "round"; c.stroke();

  // emphasised endpoint + direct label
  const last = sm[sm.length-1], lx = X(last.x), ly = Y(last.t);
  c.beginPath(); c.arc(lx, ly, 5, 0, Math.PI*2);
  c.fillStyle = accent; c.fill();
  c.lineWidth = 2.5; c.strokeStyle = surface; c.stroke();
  c.font = "600 12px " + fData;
  c.fillStyle = accent; c.textBaseline = "bottom";
  c.textAlign = lx > W - 60 ? "right" : "left";
  c.fillText(last.t.toFixed(1), lx > W - 60 ? lx - 9 : lx + 9, ly - 6);
}

function hover(ev){
  if(!pts.length){ tip.style.opacity = 0; return; }
  const r = cv.getBoundingClientRect(), mx = ev.clientX - r.left;
  let best = pts[0], bd = Infinity;
  pts.forEach(q => { const d = Math.abs(q.px - mx); if(d < bd){ bd = d; best = q; } });
  if(bd > 40){ tip.style.opacity = 0; return; }
  const rec = S.log.find(l => l.d === best.p.d);
  tip.innerHTML = thDate(best.p.d) + '<br><span class="mono">' + n1(best.p.w) + " กก.</span>"
    + '<br><span style="color:var(--ink-3)">เทรนด์ ' + n1(best.p.t) + " กก."
    + (rec && rec.k != null ? " · " + n0(rec.k) + " kcal" : "") + "</span>";
  tip.style.left = best.px + "px";
  tip.style.top = (best.py - 10) + "px";
  tip.style.opacity = 1;
}
cv.addEventListener("mousemove", hover);
cv.addEventListener("mouseleave", () => tip.style.opacity = 0);
cv.addEventListener("touchstart", e => { if(e.touches[0]) hover(e.touches[0]); }, {passive:true});
cv.addEventListener("touchmove",  e => { if(e.touches[0]) hover(e.touches[0]); }, {passive:true});

/* ═══════════════════ แท็บอาหาร ═══════════════════ */

/* ── รูปอาหารเก็บใน IndexedDB ไม่ใช่ localStorage
      localStorage มีที่ราว 5MB รูปเดียวก็เกือบเต็มแล้ว ── */
const PHOTOS = (() => {
  let dbp = null;
  function db(){
    if(dbp) return dbp;
    dbp = new Promise((res, rej) => {
      const rq = indexedDB.open("tdee-photos", 1);
      rq.onupgradeneeded = () => rq.result.createObjectStore("p", { keyPath: "id" });
      rq.onsuccess = () => res(rq.result);
      rq.onerror  = () => rej(rq.error);
    }).catch(() => null);
    return dbp;
  }
  const tx = async (mode, fn) => {
    const d = await db();
    if(!d) return null;
    return new Promise(res => {
      const t = d.transaction("p", mode), st = t.objectStore("p");
      const r = fn(st);
      t.oncomplete = () => res(r && r.result !== undefined ? r.result : true);
      t.onerror = () => res(null);
    });
  };
  return {
    put: (id, blob) => tx("readwrite", st => st.put({ id, blob })),
    get: async id => { const r = await tx("readonly", st => st.get(id)); return r && r.blob ? r.blob : null; },
    del: id => tx("readwrite", st => st.delete(id))
  };
})();

/* ย่อรูปก่อนเก็บและก่อนส่งให้ AI — รูปจากกล้องมือถือใหญ่ 3–8MB ส่งทั้งดุ้นเปลืองและช้า */
function shrink(file, max = 900, q = 0.75){
  return new Promise((res, rej) => {
    const img = new Image(), url = URL.createObjectURL(file);
    img.onload = () => {
      URL.revokeObjectURL(url);
      const sc = Math.min(1, max / Math.max(img.width, img.height));
      const cv = document.createElement("canvas");
      cv.width = Math.round(img.width * sc);
      cv.height = Math.round(img.height * sc);
      cv.getContext("2d").drawImage(img, 0, 0, cv.width, cv.height);
      cv.toBlob(b => b ? res(b) : rej(new Error("ย่อรูปไม่สำเร็จ")), "image/jpeg", q);
    };
    img.onerror = () => { URL.revokeObjectURL(url); rej(new Error("เปิดไฟล์รูปไม่ได้")); };
    img.src = url;
  });
}
const blobToB64 = blob => new Promise(res => {
  const r = new FileReader();
  r.onload = () => res(String(r.result).split(",")[1]);
  r.readAsDataURL(blob);
});

/* หน้า Artifact เสิร์ฟเป็นไฟล์เดียวและมี CSP ห้ามต่อออกนอก
   สแกนบาร์โค้ดกับ AI ดูรูปเลยใช้ไม่ได้ที่นั่น — ปิดไปเลยดีกว่าปล่อยให้กดแล้ว error */
const ARTIFACT = !!window.__TDEE_ARTIFACT__;

const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
const MEALS = ["เช้า", "กลางวัน", "เย็น", "ว่าง"];
let thumbURLs = [];

/* ── หน้าจอหลักของแท็บ ── */
function renderFood(){
  if(!$("panel-food")) return;
  if(!fday) fday = todayISO();
  $("d-cur").value = fday;

  const items = S.foods.filter(f => f.d === fday);
  const eaten = items.reduce((s, f) => s + (f.kcal || 0), 0);
  const target = targetKcal(S.goalPct);
  const m = macros();
  const got = foodMacros(fday);

  $("f-eaten").textContent  = n0(eaten);
  $("f-target").textContent = n0(target);
  const pct = Math.min(100, eaten / target * 100);
  $("f-bar").style.width = pct + "%";
  $("f-bar").parentElement.dataset.over = eaten > target ? "1" : "0";

  const left = target - eaten;
  const lf = $("f-left");
  lf.className = "bleft" + (left < 0 ? " over" : "");
  lf.innerHTML = !items.length
    ? "ยังไม่ได้บันทึกอะไรวันนี้"
    : left >= 0
      ? "เหลืออีก <b>" + n0(left) + " kcal</b> ถึงเป้าหมาย"
      : "เกินเป้าไป <b>" + n0(-left) + " kcal</b>";

  $("f-macros").innerHTML = [
    ["โปรตีน", got.p, m.proG,  "var(--m-pro)"],
    ["ไขมัน",  got.f, m.fatG,  "var(--m-fat)"],
    ["คาร์บ",  got.c, m.carbG, "var(--m-carb)"]
  ].map(([k, have, goal, col]) =>
    '<div class="mg"><div class="k"><span>' + k + '</span><b>' + n0(have) + "/" + n0(goal) + ' ก.</b></div>'
    + '<div class="t"><span style="width:' + Math.min(100, goal ? have/goal*100 : 0).toFixed(1)
    + '%;background:' + col + '"></span></div></div>'
  ).join("");

  $("foodcount").textContent = items.length ? "(" + items.length + ")" : "";
  $("f-count").textContent = items.length ? items.length + " รายการ · " + n0(eaten) + " kcal" : "";

  thumbURLs.forEach(URL.revokeObjectURL);
  thumbURLs = [];

  $("mealwrap").innerHTML = MEALS.map(meal => {
    const rows = items.filter(f => f.meal === meal);
    const kc = rows.reduce((s, f) => s + (f.kcal || 0), 0);
    return '<div class="meal"><div class="mealhead"><h3>' + meal + "</h3>"
      + '<span class="kc">' + (rows.length ? n0(kc) + " kcal" : "—") + "</span></div>"
      + (rows.length
          ? rows.map(f =>
              '<div class="fitem" data-id="' + f.id + '" role="button" tabindex="0">'
              + (f.photo ? '<img class="fthumb" data-photo="' + f.photo + '" alt="">'
                         : '<span class="fthumb ph">' + (f.src === "barcode" ? "▥" : f.src === "lib" ? "★" : "✎") + "</span>")
              + '<span class="fmain"><b>' + esc(f.name) + "</b><span>" + esc(f.qty || "")
              + (f.src === "ai" ? '<span class="srcpill">AI</span>' : "") + "</span></span>"
              + '<span class="fkc"><b>' + n0(f.kcal) + "</b><span>"
              + "P" + n0(f.p||0) + " F" + n0(f.f||0) + " C" + n0(f.c||0) + "</span></span></div>").join("")
          : '<div class="fempty">ยังไม่มี</div>')
      + "</div>";
  }).join("");

  // ใส่รูปย่อทีหลัง (อ่านจาก IndexedDB เป็น async)
  $("mealwrap").querySelectorAll("img[data-photo]").forEach(async img => {
    const b = await PHOTOS.get(img.dataset.photo);
    if(!b) return;
    const u = URL.createObjectURL(b);
    thumbURLs.push(u);
    img.src = u;
  });

  if(ARTIFACT){
    $("a-photo").disabled = true;
    $("a-scan").disabled = true;
    $("a-hint").textContent = "ถ่ายรูปกับสแกนบาร์โค้ดใช้ได้เฉพาะบนเว็บแอปที่ติดตั้งไว้";
    $("aisettings").hidden = true;
  } else {
    const ready = !!(S.ai.url && S.ai.token);
    $("a-photo").disabled = !ready;
    $("a-hint").textContent = ready ? "" : "ปุ่มถ่ายรูปต้องตั้งค่า AI ก่อน";
  }
}
const esc = t => String(t).replace(/[&<>"]/g, c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;" }[c]));

/* ── กล่องแก้ไข: ทุกวิธีเพิ่มอาหารมาจบที่นี่ เพื่อให้แก้ตัวเลขก่อนบันทึกได้เสมอ ── */
const dlgEdit = $("dlg-edit");
let editing = null;          // {id?, photo?, blobPending?}

function openEditor(data){
  editing = { id: data.id || null, photo: data.photo || null, src: data.src || "manual", barcode: data.barcode || null };
  $("ed-title").textContent = data.id ? "แก้ไขรายการ" : "เพิ่มอาหาร";
  $("ed-name").value = data.name || "";
  $("ed-qty").value  = data.qty  || "";
  $("ed-kcal").value = data.kcal != null ? Math.round(data.kcal) : "";
  $("ed-p").value = data.p != null ? Math.round(data.p * 10) / 10 : "";
  $("ed-f").value = data.f != null ? Math.round(data.f * 10) / 10 : "";
  $("ed-c").value = data.c != null ? Math.round(data.c * 10) / 10 : "";
  const meal = data.meal || guessMeal();
  const mr = document.querySelector('#ed-meal input[value="' + meal + '"]');
  if(mr) mr.checked = true;
  $("ed-del").hidden = !data.id;
  $("ed-save").checked = !data.id;
  $("ed-save").parentElement.hidden = !!data.id;
  $("ed-ai").hidden = true; $("ed-ai").innerHTML = "";
  $("ed-img").hidden = true; $("ed-img").removeAttribute("src");
  if(data.photo) showEditorPhoto(data.photo);
  edCheck();
  if(!dlgEdit.open) dlgEdit.showModal();
  if(!data.name) setTimeout(() => $("ed-name").focus(), 60);
}
async function showEditorPhoto(id){
  const b = await PHOTOS.get(id);
  if(!b) return;
  const u = URL.createObjectURL(b);
  thumbURLs.push(u);
  $("ed-img").src = u; $("ed-img").hidden = false;
}
function guessMeal(){
  const h = new Date().getHours();
  return h < 10 ? "เช้า" : h < 15 ? "กลางวัน" : h < 21 ? "เย็น" : "ว่าง";
}
/* เตือนเมื่อมาโครกับ kcal ไม่ตรงกัน — จับเลขพิมพ์ผิดได้เยอะ */
function edCheck(){
  const kcal = parseFloat($("ed-kcal").value) || 0;
  const p = parseFloat($("ed-p").value) || 0, f = parseFloat($("ed-f").value) || 0, c = parseFloat($("ed-c").value) || 0;
  const fromMacro = p*4 + f*9 + c*4;
  const el = $("ed-check");
  if(!kcal && !fromMacro){ el.className = "note"; el.innerHTML = "&nbsp;"; return; }
  if(!kcal && fromMacro){ el.className = "note"; el.textContent = "จากมาโครที่กรอก คิดเป็น " + n0(fromMacro) + " kcal — กด Tab เพื่อเติมให้"; return; }
  const diff = Math.abs(fromMacro - kcal);
  if(fromMacro && diff / kcal > 0.25){
    el.className = "note warn";
    el.textContent = "มาโครที่กรอกคิดเป็น " + n0(fromMacro) + " kcal ต่างจาก " + n0(kcal) + " ที่ใส่ไว้พอสมควร — เช็กอีกที";
  } else { el.className = "note"; el.innerHTML = "&nbsp;"; }
}
["ed-kcal","ed-p","ed-f","ed-c"].forEach(id => $(id).addEventListener("input", edCheck));
$("ed-kcal").addEventListener("blur", () => {
  if($("ed-kcal").value) return;
  const p = parseFloat($("ed-p").value)||0, f = parseFloat($("ed-f").value)||0, c = parseFloat($("ed-c").value)||0;
  const k = p*4 + f*9 + c*4;
  if(k > 0){ $("ed-kcal").value = Math.round(k); edCheck(); }
});

function saveEditor(){
  const name = $("ed-name").value.trim();
  const kcal = parseFloat($("ed-kcal").value);
  if(!name){ $("ed-name").focus(); return; }
  if(!Number.isFinite(kcal)){ $("ed-kcal").focus(); return; }
  const rec = {
    id: editing.id || uid(),
    d: fday,
    meal: document.querySelector('#ed-meal input:checked').value,
    name,
    qty: $("ed-qty").value.trim(),
    kcal,
    p: parseFloat($("ed-p").value) || 0,
    f: parseFloat($("ed-f").value) || 0,
    c: parseFloat($("ed-c").value) || 0,
    src: editing.src,
    photo: editing.photo,
    barcode: editing.barcode
  };
  const i = S.foods.findIndex(x => x.id === rec.id);
  if(i >= 0) S.foods[i] = rec; else S.foods.push(rec);

  if($("ed-save").checked && !$("ed-save").parentElement.hidden) addToLib(rec);
  dlgEdit.close();
  renderAll();
}
function addToLib(rec){
  const key = rec.barcode || rec.name.toLowerCase();
  const i = S.lib.findIndex(x => (x.barcode || x.name.toLowerCase()) === key);
  const entry = { id: i >= 0 ? S.lib[i].id : uid(), name: rec.name, qty: rec.qty,
    kcal: rec.kcal, p: rec.p, f: rec.f, c: rec.c, barcode: rec.barcode,
    n: (i >= 0 ? S.lib[i].n : 0) + 1, last: todayISO() };
  if(i >= 0) S.lib[i] = entry; else S.lib.push(entry);
}
$("ed-ok").addEventListener("click", saveEditor);
$("ed-cancel").addEventListener("click", () => dlgEdit.close());
$("ed-del").addEventListener("click", async () => {
  if(!editing.id) return;
  const rec = S.foods.find(x => x.id === editing.id);
  if(rec && rec.photo) await PHOTOS.del(rec.photo);
  S.foods = S.foods.filter(x => x.id !== editing.id);
  dlgEdit.close();
  renderAll();
});
$("mealwrap").addEventListener("click", ev => {
  const el = ev.target.closest(".fitem");
  if(!el) return;
  const rec = S.foods.find(x => x.id === el.dataset.id);
  if(rec) openEditor(rec);
});
$("mealwrap").addEventListener("keydown", ev => {
  if(ev.key !== "Enter" && ev.key !== " ") return;
  const el = ev.target.closest(".fitem");
  if(!el) return;
  ev.preventDefault();
  const rec = S.foods.find(x => x.id === el.dataset.id);
  if(rec) openEditor(rec);
});

/* ── เลือกวัน ── */
function setDay(d){ fday = d; renderFood(); }
$("d-prev").addEventListener("click", () => { const t = new Date(fday); t.setDate(t.getDate()-1); setDay(t.toISOString().slice(0,10)); });
$("d-next").addEventListener("click", () => { const t = new Date(fday); t.setDate(t.getDate()+1); setDay(t.toISOString().slice(0,10)); });
$("d-cur").addEventListener("change", () => { if($("d-cur").value) setDay($("d-cur").value); });
$("a-manual").addEventListener("click", () => openEditor({ src: "manual" }));

/* ── คลังอาหารส่วนตัว ── */
const dlgLib = $("dlg-lib");
function renderLib(){
  const q = $("lib-q").value.trim().toLowerCase();
  const rows = S.lib
    .filter(x => !q || x.name.toLowerCase().includes(q) || (x.barcode || "").includes(q))
    .sort((a, b) => (b.n - a.n) || (a.last < b.last ? 1 : -1))
    .slice(0, 60);
  $("lib-list").innerHTML = rows.length
    ? rows.map(x =>
        '<button class="libitem" type="button" data-id="' + x.id + '">'
        + '<span class="m"><b>' + esc(x.name) + "</b><span>" + esc(x.qty || "—")
        + " · กินมาแล้ว " + x.n + " ครั้ง" + (x.barcode ? " · " + x.barcode : "") + "</span></span>"
        + '<span class="kc">' + n0(x.kcal) + "</span></button>").join("")
    : '<p class="note">' + (S.lib.length ? "ไม่เจอที่ค้นหา" : "คลังยังว่าง — ทุกอย่างที่บันทึกโดยติ๊ก “เก็บเข้าคลัง” จะมาโผล่ที่นี่ กดครั้งเดียวใช้ซ้ำได้เลย") + "</p>";
}
$("a-lib").addEventListener("click", () => { $("lib-q").value = ""; renderLib(); dlgLib.showModal(); });
$("lib-q").addEventListener("input", renderLib);
$("lib-list").addEventListener("click", ev => {
  const b = ev.target.closest(".libitem");
  if(!b) return;
  const x = S.lib.find(y => y.id === b.dataset.id);
  if(!x) return;
  dlgLib.close();
  openEditor({ name: x.name, qty: x.qty, kcal: x.kcal, p: x.p, f: x.f, c: x.c,
               barcode: x.barcode, src: x.barcode ? "barcode" : "lib" });
});

/* ── บาร์โค้ด → คลังของตัวเองก่อน แล้วค่อยถาม Open Food Facts ── */
const dlgScan = $("dlg-scan");
let scanStop = null;

async function lookupBarcode(code){
  const mine = S.lib.find(x => x.barcode === code);
  if(mine) return { name: mine.name, qty: mine.qty, kcal: mine.kcal, p: mine.p, f: mine.f, c: mine.c,
                    barcode: code, src: "barcode", from: "คลังของคุณ" };
  const url = "https://world.openfoodfacts.org/api/v2/product/" + encodeURIComponent(code)
            + ".json?fields=product_name,product_name_th,brands,quantity,serving_size,nutriments";
  const r = await fetch(url);
  if(!r.ok) throw new Error("ค้นฐานข้อมูลไม่สำเร็จ (" + r.status + ")");
  const j = await r.json();
  if(j.status !== 1 || !j.product) return null;

  const pr = j.product, nu = pr.nutriments || {};
  const per = k => nu[k + "_serving"] != null ? { v: nu[k + "_serving"], s: true }
             : nu[k + "_100g"] != null ? { v: nu[k + "_100g"], s: false } : { v: null, s: false };
  const kc = per("energy-kcal"), pp = per("proteins"), ff = per("fat"), cc = per("carbohydrates");
  const useServing = kc.s;
  return {
    name: [pr.product_name_th || pr.product_name, pr.brands].filter(Boolean).join(" · ") || ("บาร์โค้ด " + code),
    qty: useServing ? (pr.serving_size || "1 หน่วยบริโภค") : "100 ก.",
    kcal: kc.v, p: pp.v, f: ff.v, c: cc.v,
    barcode: code, src: "barcode", from: "Open Food Facts"
  };
}

function scanMsg(html, cls){
  const el = $("scan-msg");
  el.className = "scanhint" + (cls ? " " + cls : "");
  el.innerHTML = html;
}

async function handleCode(code){
  stopScan();
  scanMsg('<span class="spin"></span>เจอ ' + code + " — กำลังค้นข้อมูล…");
  try{
    const hit = await lookupBarcode(code);
    if(!hit){
      dlgScan.close();
      openEditor({ name: "", qty: "1 หน่วยบริโภค", barcode: code, src: "barcode" });
      msgFood("ไม่เจอ " + code + " ในฐานข้อมูล — กรอกตัวเลขจากข้างซองเอง แล้วติ๊กเก็บเข้าคลัง ครั้งหน้าสแกนปุ๊บเจอเลย", "warn");
      return;
    }
    dlgScan.close();
    openEditor(hit);
    msgFood("เจอใน " + hit.from + (hit.qty === "100 ก." ? " — ตัวเลขเป็นต่อ 100 กรัม แก้ให้ตรงกับที่กินจริงด้วย" : ""), "good");
  }catch(e){
    scanMsg("ค้นไม่สำเร็จ: " + e.message + " — ปิดหน้านี้แล้วกรอกเองได้", "");
  }
}

async function startScan(){
  scanMsg('<span class="spin"></span>กำลังเปิดกล้อง…');
  $("scan-manual").value = "";
  if(!dlgScan.open) dlgScan.showModal();
  const video = $("scanvideo");

  let stream;
  try{
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } } });
  }catch(e){
    scanMsg("เปิดกล้องไม่ได้ (" + (e.name === "NotAllowedError" ? "ยังไม่ได้อนุญาตให้ใช้กล้อง" : e.message)
      + ") — พิมพ์เลขใต้บาร์โค้ดข้างล่างแทนได้");
    return;
  }
  video.srcObject = stream;
  await video.play().catch(() => {});

  const stopTracks = () => { stream.getTracks().forEach(t => t.stop()); video.srcObject = null; };

  if("BarcodeDetector" in window){
    let det;
    try{ det = new window.BarcodeDetector({ formats: ["ean_13","ean_8","upc_a","upc_e","code_128"] }); }
    catch{ det = new window.BarcodeDetector(); }
    let run = true;
    scanStop = () => { run = false; stopTracks(); };
    scanMsg("ส่องบาร์โค้ดให้เต็มกรอบ");
    const loop = async () => {
      if(!run) return;
      try{
        const found = await det.detect(video);
        if(found.length && found[0].rawValue){ handleCode(found[0].rawValue); return; }
      }catch{}
      setTimeout(loop, 220);
    };
    loop();
    return;
  }

  // Safari/iOS ไม่มี BarcodeDetector — โหลดตัวอ่านเพิ่มตอนนี้ (362KB โหลดครั้งเดียวแล้วแคชไว้)
  scanMsg('<span class="spin"></span>เครื่องนี้ต้องโหลดตัวอ่านบาร์โค้ดเพิ่ม (โหลดครั้งเดียว)…');
  try{
    await loadScript("vendor/zxing.min.js");
  }catch{
    scanMsg("โหลดตัวอ่านบาร์โค้ดไม่ได้ — พิมพ์เลขใต้บาร์โค้ดข้างล่างแทน");
    stopTracks();
    return;
  }
  try{
    const reader = new window.ZXing.BrowserMultiFormatReader();
    scanMsg("ส่องบาร์โค้ดให้เต็มกรอบ");
    scanStop = () => { try{ reader.reset(); }catch{} stopTracks(); };
    reader.decodeFromStream(stream, video, (res) => { if(res) handleCode(res.getText()); });
  }catch(e){
    scanMsg("ตัวอ่านบาร์โค้ดมีปัญหา: " + e.message + " — พิมพ์เลขเองได้");
    stopTracks();
  }
}
function stopScan(){ if(scanStop){ try{ scanStop(); }catch{} scanStop = null; } }
function loadScript(src){
  return new Promise((res, rej) => {
    if(document.querySelector('script[data-src="' + src + '"]')) return res();
    const el = document.createElement("script");
    el.src = src; el.dataset.src = src;
    el.onload = res; el.onerror = () => rej(new Error("load failed"));
    document.head.appendChild(el);
  });
}
$("a-scan").addEventListener("click", startScan);
$("scan-close").addEventListener("click", () => dlgScan.close());
$("scan-go").addEventListener("click", () => {
  const code = $("scan-manual").value.replace(/\D/g, "");
  if(code.length < 6){ scanMsg("เลขบาร์โค้ดสั้นเกินไป ปกติมี 8 หรือ 13 หลัก"); return; }
  handleCode(code);
});
$("scan-manual").addEventListener("keydown", e => { if(e.key === "Enter"){ e.preventDefault(); $("scan-go").click(); } });
dlgScan.addEventListener("close", stopScan);

/* ── ถ่ายรูป → ให้ Claude ประเมิน ── */
function msgFood(text, cls){
  const el = $("a-msg");
  el.hidden = false;
  el.className = "note " + (cls || "");
  el.innerHTML = text;
}
$("a-photo").addEventListener("click", () => $("photoin").click());
$("photoin").addEventListener("change", async () => {
  const file = $("photoin").files && $("photoin").files[0];
  $("photoin").value = "";
  if(!file) return;

  let blob;
  try{ blob = await shrink(file); }
  catch(e){ msgFood("ย่อรูปไม่สำเร็จ: " + e.message, "bad"); return; }

  const photoId = "ph_" + uid();
  await PHOTOS.put(photoId, blob);

  // เปิดกล่องให้เห็นรูปทันที ไม่ต้องรอ AI
  openEditor({ src: "ai", photo: photoId, qty: "1 จาน" });
  const box = $("ed-ai");
  box.hidden = false;
  box.innerHTML = '<span class="spin"></span>กำลังให้ AI ดูรูป…';

  try{
    const data = await askAI(blob);
    if(!data.ok){
      box.innerHTML = "AI บอกว่ารูปนี้ไม่ใช่อาหาร — กรอกเองได้เลย";
      return;
    }
    if(!$("ed-name").value) $("ed-name").value = data.name || "";
    const t = data.total || {};
    if(!$("ed-kcal").value) $("ed-kcal").value = Math.round(t.kcal || 0);
    if(!$("ed-p").value) $("ed-p").value = Math.round((t.protein_g || 0) * 10) / 10;
    if(!$("ed-f").value) $("ed-f").value = Math.round((t.fat_g || 0) * 10) / 10;
    if(!$("ed-c").value) $("ed-c").value = Math.round((t.carb_g || 0) * 10) / 10;
    edCheck();

    const cfTxt = { high: "มั่นใจสูง", medium: "มั่นใจปานกลาง", low: "มั่นใจต่ำ" }[data.confidence] || data.confidence;
    box.innerHTML = '<span class="cf ' + data.confidence + '">' + cfTxt + "</span>" + esc(data.note || "")
      + (data.items && data.items.length > 1
          ? '<ul class="aiitems">' + data.items.map(i =>
              "<li><span>" + esc(i.name) + " · " + esc(i.qty_desc) + '</span><span class="n">'
              + n0(i.kcal) + " kcal</span></li>").join("") + "</ul>"
          : "")
      + '<p style="margin:8px 0 0;color:var(--ink-3)">ตัวเลขนี้เป็นการประเมินจากรูป จุดที่พลาดง่ายคือปริมาณ — แก้ทับได้เลยถ้ารู้ว่าไม่ตรง</p>';
  }catch(e){
    box.innerHTML = "AI ตอบไม่ได้: " + esc(e.message) + " — กรอกเองได้เลย รูปยังเก็บไว้ให้";
  }
});

async function askAI(blob){
  if(!S.ai.url || !S.ai.token) throw new Error("ยังไม่ได้ตั้งค่า Worker");
  const b64 = await blobToB64(blob);
  const r = await fetch(S.ai.url.replace(/\/+$/, "") + "/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-App-Token": S.ai.token },
    body: JSON.stringify({ image: b64, media_type: "image/jpeg" })
  });
  const j = await r.json().catch(() => ({}));
  if(!r.ok) throw new Error(j.error || ("เซิร์ฟเวอร์ตอบ " + r.status));
  return j;
}

/* ── ตั้งค่า AI ── */
function pushAI(){ $("ai-url").value = S.ai.url || ""; $("ai-token").value = S.ai.token || ""; }
$("ai-url").addEventListener("input", () => { S.ai.url = $("ai-url").value.trim(); save(); renderFood(); });
$("ai-token").addEventListener("input", () => { S.ai.token = $("ai-token").value.trim(); save(); renderFood(); });
$("ai-clear").addEventListener("click", () => { S.ai = { url: "", token: "" }; pushAI(); save(); renderFood();
  aiMsg("ล้างค่าแล้ว", ""); });
function aiMsg(t, cls){ const el = $("ai-msg"); el.hidden = false; el.className = "note " + (cls || ""); el.innerHTML = t; }
$("ai-test").addEventListener("click", async () => {
  if(!S.ai.url || !S.ai.token){ aiMsg("กรอกให้ครบทั้งสองช่องก่อน", "warn"); return; }
  aiMsg('<span class="spin"></span>กำลังทดสอบ…', "");
  // ส่งรูปสี่เหลี่ยมจิ๋ว ๆ ไป — พอให้รู้ว่าต่อติดและรหัสถูก โดยไม่เปลืองค่า API มาก
  const cv = document.createElement("canvas");
  cv.width = cv.height = 32;
  const cx = cv.getContext("2d");
  cx.fillStyle = "#888"; cx.fillRect(0, 0, 32, 32);
  const blob = await new Promise(r => cv.toBlob(r, "image/jpeg", 0.6));
  try{
    await askAI(blob);
    aiMsg("<b>ต่อติดแล้ว</b> ปุ่มถ่ายรูปใช้ได้เลย", "good");
  }catch(e){
    aiMsg("ต่อไม่ติด: " + esc(e.message), "bad");
  }
});

/* ─────────── wiring ─────────── */
function renderAll(){ renderLabel(); renderGoals(); renderFormulas(); renderTrack(); renderFood(); save(); }

function pushInputs(){                      // state → DOM
  document.querySelector('input[name="sex"][value="' + S.sex + '"]').checked = true;
  const act = document.querySelector('input[name="act"][value="' + S.act + '"]');
  if(act) act.checked = true;
  $("i-age").value = S.age; $("i-ht").value = S.ht; $("i-wt").value = S.wt;
  $("i-bf").value = S.bf ?? ""; $("i-goalwt").value = S.goalWt ?? "";
  $("i-formula").value = S.formula;
  $("i-pro").value = S.proPerKg; $("i-fat").value = S.fatPct; $("i-meals").value = S.meals;
  syncOuts();
}
function syncOuts(){
  $("o-pro").textContent   = S.proPerKg.toFixed(1) + " ก/กก";
  $("o-fat").textContent   = S.fatPct + "%";
  $("o-meals").textContent = S.meals + " มื้อ";
}

function bindNum(id, key, min, max, allowNull){
  $(id).addEventListener("input", () => {
    const v = num($(id));
    if(v == null){ if(allowNull){ S[key] = null; renderAll(); } return; }
    if(v < min || v > max) return;           // ปล่อยให้พิมพ์ต่อ ไม่เด้ง
    S[key] = v; renderAll();
  });
}
bindNum("i-age", "age", 14, 100);
bindNum("i-ht", "ht", 120, 230);
bindNum("i-wt", "wt", 30, 300);
bindNum("i-bf", "bf", 3, 60, true);
bindNum("i-goalwt", "goalWt", 30, 300, true);

document.querySelectorAll('input[name="sex"]').forEach(el =>
  el.addEventListener("change", () => { S.sex = el.value; renderAll(); }));
document.querySelectorAll('input[name="act"]').forEach(el =>
  el.addEventListener("change", () => { S.act = parseFloat(el.value); renderAll(); }));
$("i-formula").addEventListener("change", () => {
  S.formula = $("i-formula").value;
  if(S.formula === "katch" && S.bf == null){ $("i-bf").focus(); }
  renderAll();
});
[["i-pro","proPerKg",parseFloat],["i-fat","fatPct",parseInt],["i-meals","meals",parseInt]].forEach(([id,key,fn]) =>
  $(id).addEventListener("input", () => { S[key] = fn($(id).value); syncOuts(); renderAll(); }));

$("goalbody").addEventListener("click", ev => {
  const tr = ev.target.closest("tr[data-pct]");
  if(!tr) return;
  S.goalPct = parseInt(tr.dataset.pct, 10);
  if(S.goalPct <= -20 && S.proPerKg < 2.0){ S.proPerKg = 2.0; $("i-pro").value = 2.0; syncOuts(); }
  renderAll();
});

/* tabs — รองรับลิงก์ตรง #track (ใช้กับ shortcut ของแอปที่ติดตั้งไว้) */
const TABS = [["tab-calc","panel-calc","calc"],["tab-food","panel-food","food"],["tab-track","panel-track","track"]];
function showTab(hash, push){
  const row = TABS.find(r => r[2] === hash) || TABS[0];
  TABS.forEach(([t2,p2]) => {
    const on = t2 === row[0];
    $(t2).setAttribute("aria-selected", on ? "true" : "false");
    $(p2).hidden = !on;
  });
  if(push && location.hash !== "#" + row[2])
    history.replaceState(null, "", "#" + row[2]);
  if(row[2] === "track") requestAnimationFrame(() => drawChart(adaptive()));
  if(row[2] === "food") renderFood();
}
TABS.forEach(([t,,h]) => $(t).addEventListener("click", () => showTab(h, true)));
addEventListener("hashchange", () => showTab(location.hash.slice(1), false));

/* theme */
function applyTheme(){
  if(S.theme) document.documentElement.setAttribute("data-theme", S.theme);
  else document.documentElement.removeAttribute("data-theme");
}
$("themebtn").addEventListener("click", () => {
  const dark = document.documentElement.getAttribute("data-theme") === "dark"
    || (!document.documentElement.getAttribute("data-theme") && matchMedia("(prefers-color-scheme: dark)").matches);
  S.theme = dark ? "light" : "dark";
  applyTheme(); save();
  requestAnimationFrame(() => drawChart(adaptive()));
});

/* log */
function msg(text, cls){
  const el = $("l-msg");
  el.hidden = false; el.className = "note " + (cls || "");
  el.innerHTML = text;
}
$("l-add").addEventListener("click", () => {
  const d = $("l-date").value || todayISO();
  const w = num($("l-wt")), k = num($("l-kcal"));
  if(w == null && k == null){ msg("ใส่น้ำหนักหรือ kcal อย่างน้อยอย่างหนึ่งก่อน", "warn"); return; }
  const i = S.log.findIndex(r => r.d === d);
  const rec = { d, w, k };
  if(i >= 0){
    if(w == null) rec.w = S.log[i].w;
    if(k == null) rec.k = S.log[i].k;
    S.log[i] = rec;
  } else S.log.push(rec);

  const newest = S.log.reduce((m, r) => (r.w != null && (!m || r.d > m.d)) ? r : m, null);
  let extra = "";
  if(rec.w != null && newest && newest.d === d && Math.abs(S.wt - rec.w) > 0.05){
    S.wt = rec.w; $("i-wt").value = rec.w;
    extra = " · อัปเดตน้ำหนักในแท็บคำนวณเป็น " + n1(rec.w) + " กก. ให้แล้ว";
  }
  $("l-wt").value = ""; $("l-kcal").value = "";
  $("l-date").value = todayISO();
  msg("บันทึก " + thDate(d) + " เรียบร้อย" + extra, "good");
  renderAll();
});
$("logbody").addEventListener("click", ev => {
  const b = ev.target.closest("button.del");
  if(!b) return;
  S.log = S.log.filter(r => r.d !== b.dataset.d);
  renderAll();
});

/* backup / restore — ไม่มีการส่งข้อมูลออกไปไหน */
$("l-copy").addEventListener("click", async () => {
  const json = JSON.stringify(S);
  try{
    await navigator.clipboard.writeText(json);
    msg("คัดลอกข้อมูลทั้งหมดแล้ว เอาไปวางเก็บไว้ที่ไหนก็ได้ (โน้ต/แชท) กันหาย", "good");
  }catch(e){
    showRestoreBox(json, true);
    msg("คัดลอกอัตโนมัติไม่ได้ — เลือกข้อความในกล่องด้านล่างแล้วคัดลอกเอง", "warn");
  }
});
let box = null;
function showRestoreBox(value, readonly){
  if(!box){
    box = document.createElement("textarea");
    box.rows = 4;
    box.style.cssText = "width:100%;margin-top:12px;font-family:var(--f-data);font-size:11px;"
      + "border:1px solid var(--hair);border-radius:2px;background:var(--sunk);color:var(--ink);padding:8px";
    const go = document.createElement("button");
    go.className = "btn sm"; go.type = "button"; go.textContent = "กู้ข้อมูลจากกล่องนี้";
    go.style.marginTop = "8px";
    go.addEventListener("click", () => {
      try{
        const data = JSON.parse(box.value);
        if(!data || typeof data !== "object" || !Array.isArray(data.log)) throw new Error("bad");
        Object.assign(S, data);
        pushInputs(); applyTheme(); renderAll();
        msg("กู้ข้อมูลสำเร็จ — " + S.log.length + " วัน", "good");
      }catch(e){ msg("ข้อมูลไม่ถูกต้อง — ต้องเป็นข้อความที่ได้จากปุ่ม “คัดลอกข้อมูลสำรอง”", "bad"); }
    });
    $("l-msg").insertAdjacentElement("afterend", box);
    box.insertAdjacentElement("afterend", go);
    box._go = go;
  }
  box.hidden = false; box._go.hidden = !!readonly;
  box.readOnly = !!readonly;
  box.value = value || "";
  if(readonly) box.select();
  else box.focus();
}
$("l-paste").addEventListener("click", () => {
  showRestoreBox("", false);
  msg("วางข้อความสำรองลงในกล่องด้านล่าง แล้วกดปุ่มกู้ข้อมูล — ข้อมูลปัจจุบันจะถูกทับ", "warn");
});

/* resize */
let rz;
addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => drawChart(adaptive()), 120); });

/* init */
load();
applyTheme();
pushInputs();
$("l-date").value = todayISO();
fday = todayISO();
pushAI();
renderAll();
showTab(location.hash.slice(1), false);
document.fonts && document.fonts.ready.then(() => drawChart(adaptive()));
})();
