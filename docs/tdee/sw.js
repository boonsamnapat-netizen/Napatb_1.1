/* งบแคลอรี่รายวัน — service worker
   เปลี่ยน VERSION ทุกครั้งที่แก้ไฟล์ในเชลล์ เพื่อให้เครื่องที่ติดตั้งไว้ดึงของใหม่ */
const VERSION = "tdee-2026-08-23a";
const SHELL   = VERSION + "-shell";
const FONTS   = "tdee-fonts-v1";

const ASSETS = [
  "./", "./index.html", "./app.css", "./app.js", "./pwa.js",
  "./manifest.webmanifest", "./icon.svg",
  "./icon-192.png", "./icon-512.png", "./icon-maskable-512.png", "./apple-touch-icon.png"
];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(ASSETS)));
});

self.addEventListener("activate", e => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k !== SHELL && k !== FONTS).map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener("message", e => { if (e.data === "SKIP_WAITING") self.skipWaiting(); });

const isFont = u => u.hostname === "fonts.googleapis.com" || u.hostname === "fonts.gstatic.com";

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  // ฟอนต์: ใช้ของที่แคชไว้ก่อน แล้วค่อยอัปเดตเบื้องหลัง (ออฟไลน์ก็ยังได้ฟอนต์)
  if (isFont(url)) {
    e.respondWith((async () => {
      const c = await caches.open(FONTS);
      const hit = await c.match(req);
      const net = fetch(req).then(r => { if (r.ok || r.type === "opaque") c.put(req, r.clone()); return r; }).catch(() => null);
      return hit || (await net) || Response.error();
    })());
    return;
  }

  if (url.origin !== location.origin) return;

  // การเปิดหน้า: เอาของใหม่ก่อน ถ้าเน็ตไม่มีค่อยใช้ของที่แคช
  if (req.mode === "navigate") {
    e.respondWith((async () => {
      try {
        const fresh = await fetch(req);
        (await caches.open(SHELL)).put("./index.html", fresh.clone());
        return fresh;
      } catch (err) {
        const c = await caches.open(SHELL);
        return (await c.match("./index.html")) || (await c.match("./")) || Response.error();
      }
    })());
    return;
  }

  // ไฟล์อื่นในเชลล์: แคชก่อน
  e.respondWith((async () => {
    const c = await caches.open(SHELL);
    const hit = await c.match(req);
    if (hit) return hit;
    try {
      const r = await fetch(req);
      if (r.ok) c.put(req, r.clone());
      return r;
    } catch (err) { return Response.error(); }
  })());
});
