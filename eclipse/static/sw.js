/**
 * Eclipse PWA Service Worker
 * ===========================
 * Zero-Stale-Cache Architecture:
 * - Network-First for all HTML navigation (instant updates after git pull / update)
 * - Strict bypass for all /api/* requests (live streaming, zero interception)
 * - Auto-purging on 'PURGE_AND_SKIP_WAITING' message from auto-updater
 * - Offline fallback screen for total disconnection
 */

const CACHE_VERSION = 'v1';
const CACHE_NAME = `eclipse-cache-${CACHE_VERSION}`;
const OFFLINE_URL = '/static/offline.html';

const PRECACHE_ASSETS = [
  OFFLINE_URL,
  '/static/logo.svg',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/manifest.json'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_ASSETS).catch((err) => {
        console.warn('[SW] Precache asset error (non-fatal):', err);
      });
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      );
    }).then(() => self.clients.claim())
  );
});

// Auto-Updater Hook: Wipe caches on command and activate fresh worker immediately
self.addEventListener('message', (event) => {
  if (event.data && (event.data.type === 'SKIP_WAITING' || event.data.type === 'PURGE_AND_SKIP_WAITING')) {
    caches.keys().then((keys) => {
      return Promise.all(keys.map((k) => caches.delete(k)));
    }).then(() => {
      self.skipWaiting();
    });
  }
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // 1. Only handle GET requests from our own origin
  if (req.method !== 'GET' || url.origin !== location.origin) {
    return;
  }

  // 2. STRICT API BYPASS: Never intercept or cache any backend or streaming APIs
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/v1/')) {
    return;
  }

  // 3. Navigation Requests (HTML / App Shell): Network-First
  // Ensures updates pulled by git or auto-updater are served immediately on reload
  if (req.mode === 'navigate' || req.headers.get('Accept')?.includes('text/html')) {
    event.respondWith(
      fetch(req).catch(async () => {
        const cached = await caches.match(req);
        if (cached) return cached;
        const offline = await caches.match(OFFLINE_URL);
        return offline || new Response('Offline', { status: 503, headers: { 'Content-Type': 'text/plain' } });
      })
    );
    return;
  }

  // 4. Static Assets with Version Cache-Busters (?v=...): Cache-First, Network Fallback
  // Since HTML navigation is Network-First, version bumps automatically fetch fresh assets
  // while untouched assets serve instantly from local cache.
  if (url.pathname.startsWith('/static/') && url.searchParams.has('v')) {
    event.respondWith(
      caches.match(req).then((cached) => {
        if (cached) return cached;
        return fetch(req).then((res) => {
          if (res.status === 200) {
            const clone = res.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, clone));
          }
          return res;
        }).catch(async () => {
          return (await caches.match(url.pathname)) || new Response('Asset offline', { status: 503 });
        });
      })
    );
    return;
  }

  // 5. General Static Resources: Stale-While-Revalidate
  event.respondWith(
    caches.match(req).then((cached) => {
      const fetchPromise = fetch(req).then((networkRes) => {
        if (networkRes.status === 200) {
          const clone = networkRes.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, clone));
        }
        return networkRes;
      }).catch(() => cached);
      return cached || fetchPromise;
    })
  );
});
