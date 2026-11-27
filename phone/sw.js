/* 离线缓存：核心资源优先缓存，失败回退网络。 */
const CACHE = "gt-translator-v2";
const CORE = [
  "./",
  "./index.html",
  "./style.css",
  "./app.js",
  "./vendor/jsQR.js",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png"
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(CORE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.protocol !== "http:" && url.protocol !== "https:") return;
  // WebSocket 与 API 不做缓存
  if (url.pathname.startsWith("/") && (url.port === location.port)) { /* 本地资源才走缓存 */ }
  e.respondWith(
    caches.match(e.request).then((hit) =>
      hit || fetch(e.request).then((resp) => {
        const copy = resp.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy));
        return resp;
      }).catch(() => caches.match("./index.html"))
    )
  );
});
