// SEDA24 Service Worker – App-Shell-Caching + Offline-Fallback
// CACHE_NAME wird von deploy.sh bei jedem Deploy mit Timestamp neu gesetzt (Cache-Buster).
const CACHE_NAME = 'seda24-cache-v1';

// Statische Grundausstattung, die beim Install vorab gecacht wird.
// Die gehashten JS/CSS-Bundles werden NICHT hier gelistet (Namen aendern sich je Build),
// sondern zur Laufzeit beim ersten Online-Load gecacht (siehe fetch-Handler).
const SHELL = [
  '/',
  '/index.html',
  '/offline.html',
  '/manifest.json',
  '/icon-192.png',
  '/icon-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;                    // nur GET

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;     // nur eigene Herkunft
  if (url.pathname.startsWith('/api/')) return;        // API NIE cachen – Offline-Queue der App uebernimmt

  // Navigationen (Seitenaufruf): network-first -> Cache -> Offline-Seite
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put('/index.html', copy));
          return res;
        })
        .catch(() =>
          caches.match('/index.html').then((cached) => cached || caches.match('/offline.html'))
        )
    );
    return;
  }

  // Assets (JS/CSS/Bilder/Fonts): cache-first, sonst Netz und in Cache legen
  event.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached;
      return fetch(req)
        .then((res) => {
          if (res && res.status === 200 && res.type === 'basic') {
            const copy = res.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
          }
          return res;
        })
        .catch(() => cached);
    })
  );
});
