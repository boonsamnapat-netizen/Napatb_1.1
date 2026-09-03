import { chromium } from 'playwright';
let pass=0, fail=0;
const ok=(c,m)=>{ if(c){pass++;} else {fail++;console.log("  ✗ "+m);} };
const B = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
const seed={app:"tcas70",seenIntro:true,
  settings:{targetProgram:"cu_med",watch:["cu_med"]},
  scores:{tpat1:210,bio:62,chem:55,phys:48,math1:58,eng:66,thai:60,social:64},
  venues:{bio:{seat:"6812345",place:"ร.ร.สวนกุหลาบวิทยาลัย",room:"อาคาร 3 ห้อง 402",note:"ประตูหน้า"},
          tpat1:{seat:"7000001",place:"ม.ธรรมศาสตร์ รังสิต"}},
  topics:{},q:{},tests:{},days:{},links:{},log:{},runs:[],doneLegacy:{}};
const views=["today","plan","tests","quiz","progress","settings"];

const CONTRAST = `(() => {
  const lin=c=>c<=0.04045?c/12.92:((c+0.055)/1.055)**2.4;
  const L=r=>0.2126*lin(r[0]/255)+0.7152*lin(r[1]/255)+0.0722*lin(r[2]/255);
  const CR=(a,b)=>{const x=L(a),y=L(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);};
  const unlin=c=>c<=0.0031308?c*12.92:1.055*Math.pow(c,1/2.4)-0.055;
  function oklab2rgb(Lv,A,Bv){
    const l=Math.pow(Lv+0.3963377774*A+0.2158037573*Bv,3);
    const m=Math.pow(Lv-0.1055613458*A-0.0638541728*Bv,3);
    const s2=Math.pow(Lv-0.0894841775*A-1.2914855480*Bv,3);
    return [4.0767416621*l-3.3077115913*m+0.2309699292*s2,
           -1.2684380046*l+2.6097574011*m-0.3413193965*s2,
           -0.0041960863*l-0.7034186147*m+1.7076147010*s2]
      .map(v=>Math.min(255,Math.max(0,Math.round(unlin(v)*255))));}
  const parse=str=>{const t=String(str);const m=t.match(/-?[\\d.]+/g);if(!m)return null;
    const v=m.map(Number);
    if(/^oklab/.test(t)){const r=oklab2rgb(v[0],v[1],v[2]);return v.length>3?r.concat(v[3]):r;}
    return v.slice(0,4);};
  function bgOf(n){let cur=n;const st=[];
    while(cur instanceof Element){const cs=getComputedStyle(cur);
      if(cs.backgroundImage&&cs.backgroundImage!=="none")return null;
      const c=parse(cs.backgroundColor)||[0,0,0,0];const a=c.length<4?1:c[3];
      if(a>0){st.push([[c[0],c[1],c[2]],a]);if(a>=1)break;}
      cur=cur.parentElement;}
    let base=[255,255,255];
    for(let i=st.length-1;i>=0;i--){const[rgb,a]=st[i];base=rgb.map((v,j)=>v*a+base[j]*(1-a));}
    return base;}
  const out=[];
  document.querySelectorAll("body *").forEach(n=>{
    let own=false;for(const k of n.childNodes)if(k.nodeType===3&&k.textContent.trim())own=true;
    if(!own)return;
    const b=n.getBoundingClientRect();if(!b.width||!b.height)return;
    const cs=getComputedStyle(n);
    if(cs.visibility==="hidden"||cs.opacity==="0")return;
    const fg=parse(cs.color);if(!fg)return;
    const bg=bgOf(n);if(!bg)return;
    let f=[fg[0],fg[1],fg[2]];
    const eff=(fg.length>3?fg[3]:1)*Math.min(1,parseFloat(cs.opacity));
    if(eff<1)f=f.map((c,i)=>c*eff+bg[i]*(1-eff));
    const size=parseFloat(cs.fontSize),w=parseInt(cs.fontWeight)||400;
    const need=(size>=24||(size>=18.66&&w>=700))?3:4.5;
    const cr=CR(f,bg);
    if(cr<need)out.push((n.className||n.tagName)+" "+cr.toFixed(2)+"/"+need+" «"+n.textContent.trim().slice(0,26)+"»");
  });
  return out;
})()`;

for (const theme of ["light","dark"]) {
  for (const w of [320, 390]) {
    const ctx=await B.newContext({viewport:{width:w,height:844},colorScheme:theme,reducedMotion:'reduce'});
    const p=await ctx.newPage();
    const errs=[]; p.on("pageerror",e=>errs.push(e.message));
    await p.addInitScript(s=>localStorage.setItem("tcas70.v1",JSON.stringify(s)),seed);
    await p.goto('http://localhost:8765/',{waitUntil:'networkidle'});
    await p.waitForTimeout(400);
    for (const v of views) {
      await p.evaluate(n=>go(n),v); await p.waitForTimeout(220);
      const r = await p.evaluate(()=>{
        const de=document.documentElement;
        const small=[];
        document.querySelectorAll("button,a[href],input,select,textarea").forEach(n=>{
          const b=n.getBoundingClientRect(); if(!b.width) return;
          let W=b.width,H=b.height;
          const cs=getComputedStyle(n,"::before");
          if(cs.content!=="none"&&cs.position==="absolute"){
            W=Math.max(W,parseFloat(cs.width)||0);H=Math.max(H,parseFloat(cs.height)||0);}
          if(H<39.5) small.push((n.className||n.tagName)+" "+Math.round(W)+"x"+Math.round(H));
        });
        return {over: de.scrollWidth>de.clientWidth+1, small};
      });
      ok(!r.over, `[${theme} ${w}] ${v}: สกรอลล์แนวนอน`);
      ok(r.small.length===0, `[${theme} ${w}] ${v}: ปุ่มเตี้ยกว่า 40px → ${[...new Set(r.small)].join(", ")}`);
      const bad = await p.evaluate(CONTRAST);
      ok(bad.length===0, `[${theme} ${w}] ${v}: คอนทราสต์ตก → ${bad.slice(0,3).join(" | ")}`);
    }
    ok(errs.length===0, `[${theme} ${w}] JS error: ${errs.slice(0,2).join(" | ")}`);
    await ctx.close();
  }
}
console.log(`รวม ${pass} ผ่าน / ${fail} ไม่ผ่าน`);
await B.close();
process.exit(fail?1:0);
