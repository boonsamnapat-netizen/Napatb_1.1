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
  log: [], theme: null
};

function load(){
  try{
    const raw = localStorage.getItem(KEY);
    if(raw) Object.assign(S, JSON.parse(raw));
  }catch(e){/* private mode / blocked storage — carry on with defaults */}
  if(!Array.isArray(S.log)) S.log = [];
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

  const eats = S.log.filter(r => r.k != null && dayNum(r.d) > last - WINDOW);
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
    $("a-tdee").innerHTML = n0(a.tdee) + ' <small style="font-size:12px;color:var(--ink-3)">kcal</small>';
  } else set("a-tdee", "—", "ต้องมีน้ำหนัก + kcal อย่างน้อย 10 วัน");

  set("a-trend", a.sm.length ? n1(a.trendW) + " " : "—", a.sm.length ? "กก. · ล่าสุด " + thDate(a.sm[a.sm.length-1].d) : "ยังไม่มีข้อมูล");
  if(a.sm.length) $("a-trend").innerHTML = n1(a.trendW) + ' <small style="font-size:12px;color:var(--ink-3)">กก.</small>';

  if(a.slope != null){
    const kw = a.slope * 7;
    $("a-rate").innerHTML = (kw > 0 ? "+" : "") + n1(kw) + ' <small style="font-size:12px;color:var(--ink-3)">กก./สัปดาห์</small>';
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
  const rows = S.log.slice().sort((a,b) => a.d < b.d ? 1 : -1);
  $("logcount").textContent = S.log.length ? "(" + S.log.length + ")" : "";
  $("log-hint").textContent = S.log.length ? S.log.length + " วัน" : "";
  $("logbody").innerHTML = rows.length
    ? rows.map(r => '<tr><td>' + thDate(r.d) + "</td><td>" + (r.w != null ? n1(r.w) : "—")
        + "</td><td>" + (r.k != null ? n0(r.k) : "—")
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

  if(sm.length < 2){
    c.fillStyle = inkMuted;
    c.font = '13px "IBM Plex Sans Thai", sans-serif';
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
  c.font = '11px "IBM Plex Mono", monospace';
  c.textAlign = "right"; c.textBaseline = "middle";
  for(let i = 0; i <= 3; i++){
    const v = y0 + (y1 - y0) * i / 3, y = Math.round(Y(v)) + 0.5;
    c.beginPath(); c.moveTo(padL, y); c.lineTo(W - padR, y); c.stroke();
    c.fillText(v.toFixed(1), padL - 8, y);
  }
  // x labels: first & last
  c.textAlign = "left"; c.textBaseline = "top";
  c.font = '11px "IBM Plex Sans Thai", sans-serif';
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
  c.font = '600 12px "IBM Plex Mono", monospace';
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

/* ─────────── wiring ─────────── */
function renderAll(){ renderLabel(); renderGoals(); renderFormulas(); renderTrack(); save(); }

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
const TABS = [["tab-calc","panel-calc","calc"],["tab-track","panel-track","track"]];
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
    box.style.cssText = "width:100%;margin-top:12px;font-family:'IBM Plex Mono',monospace;font-size:11px;"
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
renderAll();
showTab(location.hash.slice(1), false);
document.fonts && document.fonts.ready.then(() => drawChart(adaptive()));
})();
