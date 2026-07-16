const STATIC_CACHE = 'peredacha-static-v3';
const PAGE_CACHE = 'peredacha-pages-v3';
const STATIC_ASSETS = [
  '/static/site.webmanifest',
  '/static/brand-logo.png',
  '/static/apple-touch-icon.png',
  '/static/favicon-32x32.png',
  '/static/favicon-16x16.png',
  '/static/apple-splash.png',
  '/login',
];
const OFFLINE_NOTICE_SCRIPT = "<script>window.__CRM_OFFLINE_FALLBACK__=true;document.documentElement.classList.add('crm-offline-fallback');</script>";
const OFFLINE_HTML = `<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
  <meta name="theme-color" content="#f9fbf5">
  <title>Передача</title>
  <style>
    :root { color-scheme: light; }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 1.25rem;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at 18% 18%, rgba(141, 214, 44, .18), transparent 17rem),
        radial-gradient(circle at 82% 20%, rgba(141, 214, 44, .16), transparent 15rem),
        linear-gradient(180deg, #fefdfe 0%, #f7faef 100%);
      color: #1f2937;
    }
    .offline-card {
      width: min(100%, 26rem);
      padding: 1.4rem;
      border-radius: 1.6rem;
      background: rgba(255, 255, 255, .92);
      border: 1px solid rgba(200, 211, 232, .64);
      box-shadow: 0 24px 64px rgba(31, 45, 61, .14);
      text-align: center;
    }
    .offline-logo {
      width: 4.5rem;
      height: 4.5rem;
      margin: 0 auto 1rem;
      border-radius: 1.25rem;
      overflow: hidden;
      box-shadow: 0 18px 42px rgba(141, 214, 44, .22);
    }
    .offline-logo img {
      width: 100%;
      height: 100%;
      display: block;
      object-fit: cover;
    }
    h1 {
      margin: 0 0 .7rem;
      font-size: 1.35rem;
      line-height: 1.2;
    }
    p {
      margin: 0;
      color: #4b5563;
      line-height: 1.45;
    }
  </style>
</head>
<body>
  <main class="offline-card">
    <div class="offline-logo">
      <img src="/static/brand-logo.png" width="96" height="96" alt="">
    </div>
    <h1>Не удается обновить</h1>
    <p>Нет интернета и сохраненной версии этой страницы тоже нет. Подключитесь к сети и попробуйте снова.</p>
  </main>
</body>
</html>`;

const withSearch = request => new Request(request.url, { method: 'GET', credentials: 'same-origin' });
const withoutSearch = request => {
  const url = new URL(request.url);
  return new Request(`${url.origin}${url.pathname}`, { method: 'GET', credentials: 'same-origin' });
};

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then(cache => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
      .catch(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys
      .filter(key => ![STATIC_CACHE, PAGE_CACHE].includes(key))
      .map(key => caches.delete(key)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', event => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (/^\/objects\/\d+\/open\/?$/.test(url.pathname)) {
    return;
  }

  if (request.mode === 'navigate' || isHtmlRequest(request)) {
    event.respondWith(handleHtmlRequest(request));
    return;
  }

  if (url.pathname.startsWith('/static/')) {
    event.respondWith(handleStaticRequest(request));
  }
});

function isHtmlRequest(request) {
  const accept = request.headers.get('accept') || '';
  return accept.includes('text/html') || request.headers.get('X-CRM-Partial-Navigation') === '1';
}

async function handleStaticRequest(request) {
  const cache = await caches.open(STATIC_CACHE);
  const url = new URL(request.url);
  const isVersionedAsset = /\.(?:css|js)$/i.test(url.pathname);
  const cached = await cache.match(request, { ignoreSearch: !isVersionedAsset });
  const fetchPromise = fetch(request)
    .then(response => {
      if (response && response.ok) cache.put(request, response.clone()).catch(() => {});
      return response;
    })
    .catch(() => cached);
  return isVersionedAsset ? fetchPromise : (cached || fetchPromise);
}

async function handleHtmlRequest(request) {
  const cache = await caches.open(PAGE_CACHE);
  const requestWithSearch = withSearch(request);
  const requestWithoutSearch = withoutSearch(request);

  try {
    const networkResponse = await fetchWithTimeout(requestWithSearch, 4500);
    if (networkResponse && networkResponse.ok) {
      cache.put(requestWithSearch, networkResponse.clone()).catch(() => {});
      cache.put(requestWithoutSearch, networkResponse.clone()).catch(() => {});
      return networkResponse;
    }
    throw new Error(`HTTP ${networkResponse?.status || 0}`);
  } catch (error) {
    const cached = await cache.match(requestWithSearch) || await cache.match(requestWithoutSearch) || await caches.match('/login');
    if (cached) return buildOfflineFallbackResponse(cached, request.mode === 'navigate');
    return new Response(OFFLINE_HTML, {
      status: 503,
      headers: {
        'Content-Type': 'text/html; charset=utf-8',
        'Cache-Control': 'no-store',
        'X-CRM-Offline-Fallback': '1',
      },
    });
  }
}

async function buildOfflineFallbackResponse(response, injectIntoHtml) {
  const headers = new Headers(response.headers);
  headers.set('X-CRM-Offline-Fallback', '1');

  const contentType = headers.get('Content-Type') || '';
  if (!injectIntoHtml || !contentType.includes('text/html')) {
    return new Response(await response.blob(), {
      status: response.status || 200,
      statusText: response.statusText || 'OK',
      headers,
    });
  }

  let html = await response.text();
  if (!html.includes('window.__CRM_OFFLINE_FALLBACK__=true')) {
    html = html.includes('</head>')
      ? html.replace('</head>', `${OFFLINE_NOTICE_SCRIPT}</head>`)
      : `${OFFLINE_NOTICE_SCRIPT}${html}`;
  }

  headers.set('Content-Type', 'text/html; charset=utf-8');
  return new Response(html, {
    status: response.status || 200,
    statusText: response.statusText || 'OK',
    headers,
  });
}

function fetchWithTimeout(request, timeoutMs) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('timeout')), timeoutMs);
    fetch(request)
      .then(response => {
        clearTimeout(timer);
        resolve(response);
      })
      .catch(error => {
        clearTimeout(timer);
        reject(error);
      });
  });
}
