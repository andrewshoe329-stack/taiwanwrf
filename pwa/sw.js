// Service worker for Taiwan Sail & Surf Forecast PWA
// Strategy: stale-while-revalidate for HTML, network-first for other assets

const CACHE_NAME = 'tw-forecast-v6';
const PRECACHE_URLS = [
  '/',
  '/hourly',
  '/surf',
  '/accuracy',
  '/spots/fulong',
  '/spots/greenbay',
  '/spots/jinshan',
  '/spots/daxi',
  '/spots/wushih',
  '/spots/doublelions',
  '/spots/chousui',
  '/manifest.json',
  '/icon-192.png',
  '/icon-512.png',
  '/styles.css',
  '/app.js'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return Promise.all(
        PRECACHE_URLS.map((url) =>
          cache.add(url).catch(() => console.warn('SW: failed to precache', url))
        )
      );
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      );
    })
  );
  self.clients.claim();
});

function isHtmlRequest(request) {
  const accept = request.headers.get('Accept') || '';
  const url = new URL(request.url);
  return accept.includes('text/html') || url.pathname === '/' ||
    !url.pathname.includes('.');
}

self.addEventListener('fetch', (event) => {
  if (isHtmlRequest(event.request)) {
    // Stale-while-revalidate for HTML: serve cached first, update in background
    event.respondWith(
      caches.match(event.request).then((cached) => {
        const networkFetch = fetch(event.request).then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return response;
        }).catch(() => null);

        if (cached) {
          // Serve stale cache immediately, notify clients
          self.clients.matchAll().then((clients) => {
            clients.forEach((client) => {
              client.postMessage({ type: 'CACHE_HIT' });
            });
          });
          // Revalidate in background (update cache for next visit)
          networkFetch.catch(() => {});
          return cached;
        }

        // No cache: wait for network, or show offline message
        return networkFetch.then((response) => {
          if (response) return response;
          return new Response(
            '<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">' +
            '<title>Offline</title><style>body{background:#0f172a;color:#e2e8f0;font-family:system-ui;' +
            'display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;text-align:center}' +
            '</style></head><body><div><h1>You are offline</h1>' +
            '<p>Please check your internet connection and try again.</p></div></body></html>',
            { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
          );
        });
      })
    );
  } else {
    // Network-first for other assets (CSS, JS, images, JSON)
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return response;
        })
        .catch(() => {
          return caches.match(event.request);
        })
    );
  }
});
