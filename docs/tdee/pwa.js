/* ติดตั้งเป็นแอป · อัปเดตเบื้องหลัง · สีแถบสถานะตามธีม */
(function(){
"use strict";
const $ = id => document.getElementById(id);
const toastEl = $("toast");
let hideTimer = null;

function toast(text, actionLabel, onAction, sticky){
  toastEl.innerHTML = "";
  const span = document.createElement("span");
  span.textContent = text;
  toastEl.appendChild(span);
  if(actionLabel){
    const b = document.createElement("button");
    b.type = "button"; b.textContent = actionLabel;
    b.addEventListener("click", () => { hide(); onAction && onAction(); });
    toastEl.appendChild(b);
  }
  toastEl.dataset.on = "1";
  clearTimeout(hideTimer);
  if(!sticky) hideTimer = setTimeout(hide, 6000);
}
function hide(){ toastEl.dataset.on = "0"; }

/* ── ติดตั้ง ── */
const btn = $("installbtn");
const standalone = matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
let deferred = null;

addEventListener("beforeinstallprompt", e => {
  e.preventDefault();
  deferred = e;
  btn.hidden = false;
});
btn.addEventListener("click", async () => {
  if(deferred){
    deferred.prompt();
    const { outcome } = await deferred.userChoice;
    deferred = null;
    if(outcome === "accepted") btn.hidden = true;
    return;
  }
  toast("กดปุ่มแชร์ของ Safari แล้วเลือก “เพิ่มไปยังหน้าจอโฮม” — จะได้ไอคอนแอปเปิดใช้ได้แม้ไม่มีเน็ต", "เข้าใจแล้ว", null, true);
});
if(isIOS && !standalone) btn.hidden = false;

addEventListener("appinstalled", () => { btn.hidden = true; toast("ติดตั้งแล้ว — เปิดจากไอคอนบนหน้าจอโฮมได้เลย"); });

/* ── service worker ── */
if("serviceWorker" in navigator && location.protocol !== "file:"){
  addEventListener("load", async () => {
    try{
      const reg = await navigator.serviceWorker.register("sw.js");
      if(!navigator.serviceWorker.controller){
        reg.addEventListener("updatefound", () => {
          const sw = reg.installing;
          sw && sw.addEventListener("statechange", () => {
            if(sw.state === "activated") toast("พร้อมใช้แบบออฟไลน์แล้ว");
          });
        });
      }
      const offerUpdate = sw => toast("มีเวอร์ชันใหม่", "อัปเดต", () => sw.postMessage("SKIP_WAITING"), true);
      if(reg.waiting) offerUpdate(reg.waiting);
      reg.addEventListener("updatefound", () => {
        const sw = reg.installing;
        sw && sw.addEventListener("statechange", () => {
          if(sw.state === "installed" && navigator.serviceWorker.controller) offerUpdate(sw);
        });
      });
      let reloading = false;
      navigator.serviceWorker.addEventListener("controllerchange", () => {
        if(reloading) return;
        reloading = true; location.reload();
      });
      setInterval(() => reg.update(), 60 * 60 * 1000);
    }catch(e){ /* ไม่มี SW ก็ยังใช้งานได้ตามปกติ */ }
  });
}

/* ── สีแถบสถานะตามธีมที่เลือกเอง ── */
const COLORS = { light: "#F1F2F7", dark: "#0B0C11" };
let override = null;
function syncThemeColor(){
  const t = document.documentElement.getAttribute("data-theme");
  if(t && COLORS[t]){
    if(!override){
      override = document.createElement("meta");
      override.name = "theme-color";
      document.head.prepend(override);          // มาก่อน = ชนะ media query
    }
    override.content = COLORS[t];
  } else if(override){
    override.remove(); override = null;
  }
}
new MutationObserver(syncThemeColor).observe(document.documentElement, { attributes:true, attributeFilter:["data-theme"] });
syncThemeColor();
})();
