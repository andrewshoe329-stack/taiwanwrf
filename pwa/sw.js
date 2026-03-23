// Service worker for Taiwan Sail & Surf Forecast PWA
// Strategy: network-first with cache fallback (always try fresh data)

const CACHE_NAME = 'tw-forecast-v4';
const PRECACHE_URLS = [
  '/', '/manifest.json', '/icon-192.png', '/icon-512.png', '/styles.css'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_URLS);
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

self.addEventListener('fetch', (event) => {
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Cache successful responses for offline use
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => {
        // Offline: notify clients we're serving cached data
        return caches.match(event.request).then((cached) => {
          if (cached) {
            self.clients.matchAll().then((clients) => {
              clients.forEach((client) => {
                client.postMessage({ type: 'CACHE_HIT' });
              });
            });
          }
          return cached;
        });
      })
  );
});
