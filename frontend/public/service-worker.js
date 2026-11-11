// SEDA24 Service Worker – App-Shell-Caching + Offline-Start
// CACHE_NAME und PRECACHE werden von deploy.sh bei jedem Deploy neu gesetzt.
// PRECACHE enthaelt die gehashten JS/CSS-Bundles des aktuellen Builds, damit die App
// nach jedem Deploy auch ohne Netz vollstaendig startet.
const CACHE_NAME = 'seda24-cache-v1';
const PRECACHE = [];

// Statische Grundausstattung
const SHELL = [
  '/',
  '/index.html',
  '/offline.html',
  '/manifest.json',
  '/icon-192.png',
  '/icon-512.png',
];

const ALL_URLS = SHELL.concat(PRECACHE);
const NAV_TIMEOUT_MS = 4000;   // schwaches Netz: nach 4 s die gecachte App starten

const reload = (url) => new Request(url, { cache: 'reload' });

// Install: neuen Cache VOLLSTAENDIG befuellen. Schlaegt eine Datei fehl, scheitert die
// Installation und der bisherige Service Worker samt Cache bleibt unveraendert aktiv.
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(ALL_URLS.map(reload)))
      .then(() => self.skipWaiting())
  );
});

async function missingUrls(cache) {
  const missing = [];
  for (const url of ALL_URLS) {
    if (!(await cache.match(url, { ignoreSearch: true }))) missing.push(url);
  }
  return missing;
}

// Activate: alte Caches erst loeschen, wenn der neue Cache nachweislich komplett ist.
self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    let missing = await missingUrls(cache);
    if (missing.length) {
      try { await cache.addAll(missing.map(reload)); } catch (e) { /* offline: spaeter */ }
      missing = await missingUrls(cache);
    }
    if (missing.length === 0) {
      const keys = await caches.keys();
      await Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)));
    }
    await self.clients.claim();
  })());
});

// Gecachte App-Seite dieses Service Workers (passt immer zu seinen Bundles)
function cachedShell() {
  return caches.open(CACHE_NAME)
    .then((cache) => cache.match('/index.html'))
    .then((res) => res || caches.match('/index.html'))
    .then((res) => res || caches.match('/offline.html'));
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;                    // nur GET

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;     // nur eigene Herkunft
  if (url.pathname.startsWith('/api/')) return;        // API NIE cachen – Offline-Queue der App uebernimmt

  // Navigationen (Seitenaufruf): Netz mit Zeitlimit, sonst gecachte App-Seite.
  // Die gecachte index.html wird NUR beim Install gesetzt, damit sie immer zu den
  // vorab gecachten Bundles passt.
  if (req.mode === 'navigate') {
    event.respondWith(new Promise((resolve) => {
      let done = false;
      const fallback = () => {
        if (done) return;
        done = true;
        cachedShell().then(resolve);
      };
      const timer = setTimeout(fallback, NAV_TIMEOUT_MS);
      fetch(req)
        .then((res) => {
          clearTimeout(timer);
          if (done) return;
          if (res && res.ok) { done = true; resolve(res); } else fallback();
        })
        .catch(() => { clearTimeout(timer); fallback(); });
    }));
    return;
  }

  // Gehashte Bundles (/assets/): Name aendert sich je Build -> Query (?v=) ignorieren
  const isAsset = url.pathname.startsWith('/assets/');

  // Assets (JS/CSS/Bilder/Fonts): cache-first (alle Caches), sonst Netz und in Cache legen
  event.respondWith(
    caches.match(req, { ignoreSearch: isAsset }).then((cached) => {
      if (cached) return cached;
      return fetch(req)
        .then((res) => {
          if (res && res.status === 200 && res.type === 'basic') {
            const copy = res.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
          }
          return res;
        });
    })
  );
});
