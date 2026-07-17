const STATIC_CACHE = 'peredacha-static-v9';
const STATIC_ASSETS = [
  '/static/site.webmanifest',
  '/static/brand-logo.png',
  '/static/apple-touch-icon.png',
  '/static/favicon-32x32.png',
  '/static/favicon-16x16.png',
  '/static/apple-splash.png',
  '/static/vendor/bootstrap/bootstrap.min.css?v=5.3.3',
  '/static/vendor/bootstrap/bootstrap-icons.min.css?v=1.11.3',
  '/static/vendor/bootstrap/bootstrap.bundle.min.js?v=5.3.3',
  '/static/vendor/bootstrap/fonts/bootstrap-icons.woff2',
  '/static/vendor/bootstrap/fonts/bootstrap-icons.woff',
  '/static/style.css?v=v602-mobile-conflict-cleanup',
  '/static/mobile-only.css?v=v3-mobile-conflict-cleanup',
  '/static/desktop-only.css?v=v2-material-request-input-white',
  '/static/script.js?v=v602-mobile-actions-cache-reset',
];

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(STATIC_CACHE);
    await Promise.allSettled(STATIC_ASSETS.map(asset => cache.add(asset)));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys
      .filter(key => key.startsWith('peredacha-') && key !== STATIC_CACHE)
      .map(key => caches.delete(key)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', event => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin || !url.pathname.startsWith('/static/')) return;

  event.respondWith(staticNetworkFirst(request));
});

async function staticNetworkFirst(request) {
  const cache = await caches.open(STATIC_CACHE);
  try {
    const response = await fetch(request);
    if (response && response.ok) await cache.put(request, response.clone());
    return response;
  } catch (error) {
    const url = new URL(request.url);
    const ignoreSearch = !/\.(?:css|js)$/i.test(url.pathname);
    const cached = await cache.match(request, { ignoreSearch });
    if (cached) return cached;
    throw error;
  }
}
