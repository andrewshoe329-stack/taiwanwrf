// Service Worker for Taiwan WRF Forecast PWA
const CACHE_NAME = 'tw-forecast-v1'
const PRECACHE_URLS = ['/', '/manifest.json', '/icon.svg']

// ── Install: precache app shell ─────────────────────────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      // Add each URL individually so one failure doesn't block the rest
      Promise.allSettled(
        PRECACHE_URLS.map((url) => cache.add(url).catch(() => {
          console.warn('SW: failed to precache', url)
        }))
      )
    )
  )
  self.skipWaiting()
})

// ── Activate: clean up old caches ───────────────────────────────────────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  )
  self.clients.claim()
})

// ── Fetch strategies ────────────────────────────────────────────────────────

function networkFirst(request) {
  return fetch(request)
    .then((response) => {
      if (response.ok) {
        const clone = response.clone()
        caches.open(CACHE_NAME).then((cache) => cache.put(request, clone))
      }
      return response
    })
    .catch(() => caches.match(request))
}

function cacheFirst(request) {
  return caches.match(request).then((cached) => {
    if (cached) return cached
    return fetch(request).then((response) => {
      if (response.ok || response.type === 'opaque') {
        const clone = response.clone()
        caches.open(CACHE_NAME).then((cache) => cache.put(request, clone))
      }
      return response
    })
  })
}

function cacheFirstWithExpiry(request, maxAgeMs) {
  return caches.match(request).then((cached) => {
    if (cached) {
      const dateHeader = cached.headers.get('date')
      if (dateHeader) {
        const age = Date.now() - new Date(dateHeader).getTime()
        if (age < maxAgeMs) return cached
      } else {
        return cached
      }
    }
    return fetch(request).then((response) => {
      // Cache opaque responses for cross-origin fonts
      if (response.ok || response.type === 'opaque') {
        const clone = response.clone()
        caches.open(CACHE_NAME).then((cache) => cache.put(request, clone))
      }
      return response
    }).catch(() => cached || undefined)
  })
}

self.addEventListener('fetch', (event) => {
  const { request } = event
  const url = new URL(request.url)

  // Only handle GET requests
  if (request.method !== 'GET') return

  // Data JSON files: network-first (stale data better than no data)
  if (url.pathname.startsWith('/data/') && url.pathname.endsWith('.json')) {
    event.respondWith(networkFirst(request))
    return
  }

  // Vite hashed assets: cache-first (immutable)
  if (url.pathname.startsWith('/assets/')) {
    event.respondWith(cacheFirst(request))
    return
  }

  // Fonts and external resources: cache-first with 7-day expiry
  if (
    url.hostname !== self.location.hostname ||
    url.pathname.match(/\.(woff2?|ttf|otf|eot)$/)
  ) {
    const sevenDays = 7 * 24 * 60 * 60 * 1000
    event.respondWith(cacheFirstWithExpiry(request, sevenDays))
    return
  }

  // Navigation requests: network-first, fall back to cached index.html for SPA
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const clone = response.clone()
          caches.open(CACHE_NAME).then((cache) => cache.put('/', clone))
          return response
        })
        .catch(() => caches.match('/').then((r) => r || caches.match('/index.html')))
    )
    return
  }

  // Default: network-first
  event.respondWith(networkFirst(request))
})
