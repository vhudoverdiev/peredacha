const STATIC_CACHE = 'peredacha-static-v8';
const PAGE_CACHE = 'peredacha-pages-v8';
const LEGACY_PAGE_CACHES = ['peredacha-pages-v7', 'peredacha-pages-v6', 'peredacha-pages-v5', 'peredacha-pages-v4', 'peredacha-pages-v3'];
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
const APP_SHELL_PAGES = ['/', '/object', '/objects', '/login'];
const MOBILE_OFFLINE_STYLE = `<style data-crm-offline-mobile-style>
  #crmMobileOfflineExperience { display: none; }

  @media (max-width: 767.98px) {
    html.crm-offline-mobile-experience,
    html.crm-offline-mobile-experience body {
      overflow: hidden !important;
      overscroll-behavior: none !important;
      background: #f3f8ec !important;
    }

    html.crm-offline-mobile-experience body > :not(#crmMobileOfflineExperience) {
      pointer-events: none !important;
    }

    html.crm-offline-mobile-experience .crm-offline-banner {
      display: none !important;
    }

    #crmMobileOfflineExperience {
      position: fixed;
      inset: -1px;
      z-index: 2147483647;
      display: grid;
      place-items: center;
      box-sizing: border-box;
      width: calc(100vw + 2px);
      height: calc(100vh + 2px);
      height: calc(100dvh + 2px);
      min-height: calc(100vh + 2px);
      padding: max(1.2rem, env(safe-area-inset-top)) 1.15rem max(1.2rem, env(safe-area-inset-bottom));
      overflow: hidden;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
      color: #172033;
      background:
        radial-gradient(circle at 12% 10%, rgba(141, 214, 44, .22), transparent 15rem),
        radial-gradient(circle at 92% 84%, rgba(141, 214, 44, .13), transparent 17rem),
        linear-gradient(160deg, #fbfef7 0%, #f3f8ec 48%, #eef5e6 100%);
      isolation: isolate;
    }

    #crmMobileOfflineExperience::before,
    #crmMobileOfflineExperience::after {
      content: "";
      position: absolute;
      z-index: -1;
      border-radius: 999px;
      filter: blur(1px);
      pointer-events: none;
    }

    #crmMobileOfflineExperience::before {
      width: 15rem;
      height: 15rem;
      top: -7.5rem;
      right: -6rem;
      border: 1px solid rgba(141, 214, 44, .2);
      box-shadow: 0 0 0 2.8rem rgba(141, 214, 44, .035), 0 0 0 5.6rem rgba(141, 214, 44, .025);
    }

    #crmMobileOfflineExperience::after {
      width: 11rem;
      height: 11rem;
      bottom: -6rem;
      left: -4.8rem;
      background: rgba(255, 255, 255, .5);
      box-shadow: 0 1.4rem 4rem rgba(31, 45, 61, .08);
    }

    .crm-mobile-offline-panel {
      position: absolute;
      left: 50%;
      top: 50%;
      box-sizing: border-box;
      width: min(calc(100% - 2.3rem), 25rem);
      transform: translate(-50%, -50%);
      transition: opacity .34s ease, transform .42s cubic-bezier(.2, .75, .24, 1);
    }

    .crm-mobile-offline-loader {
      display: grid;
      width: 100%;
      justify-items: center;
    }

    .crm-mobile-offline-loader .site-page-loader-card {
      width: min(64vw, 19.5rem);
      min-width: 15rem;
      aspect-ratio: 1;
      display: grid;
      place-items: center;
      border: 1px solid rgba(210, 224, 199, .92);
      border-radius: clamp(2rem, 7vw, 3.5rem);
      background: rgba(255, 255, 255, .8);
      box-shadow: 0 34px 95px rgba(31, 45, 61, .18);
      backdrop-filter: blur(18px);
      -webkit-backdrop-filter: blur(18px);
      animation: siteLoaderCardIn .5s ease both;
    }

    .crm-mobile-offline-loader .mobile-loading-orbit {
      position: relative;
      display: grid;
      width: clamp(8.5rem, 30vw, 11rem);
      height: clamp(8.5rem, 30vw, 11rem);
      place-items: center;
    }

    .crm-mobile-offline-loader .mobile-loading-orbit::before,
    .crm-mobile-offline-loader .mobile-loading-orbit::after,
    .crm-mobile-offline-loader .mobile-loading-orbit > span {
      content: "";
      position: absolute;
      inset: 0;
      border: 2px solid transparent;
      border-radius: 50%;
    }

    .crm-mobile-offline-loader .mobile-loading-orbit::before {
      border-top-color: rgba(141, 214, 44, .92);
      border-right-color: rgba(141, 214, 44, .24);
      animation: mobileLoaderSpin 1.15s linear infinite;
    }

    .crm-mobile-offline-loader .mobile-loading-orbit::after {
      inset: .75rem;
      border-bottom-color: rgba(141, 214, 44, .9);
      border-left-color: rgba(141, 214, 44, .22);
      animation: mobileLoaderSpin 1.7s linear infinite reverse;
    }

    .crm-mobile-offline-loader .mobile-loading-orbit > span:nth-child(1) {
      inset: 1.55rem;
      border-top-color: rgba(124, 58, 237, .42);
      animation: mobileLoaderPulse 1.6s ease-in-out infinite;
    }

    .crm-mobile-offline-loader .mobile-loading-orbit > span:nth-child(2) {
      inset: -.35rem;
      border-right-color: rgba(141, 214, 44, .18);
      animation: mobileLoaderPulse 1.9s ease-in-out infinite .18s;
    }

    .crm-mobile-offline-loader .mobile-loading-orbit > span:nth-child(3) {
      inset: 2.25rem;
      background: radial-gradient(circle, rgba(141, 214, 44, .1), transparent 68%);
      animation: mobileLoaderGlow 1.45s ease-in-out infinite alternate;
    }

    .crm-mobile-offline-loader .mobile-loading-mark {
      display: grid;
      width: clamp(4.2rem, 15vw, 5.35rem);
      height: clamp(4.2rem, 15vw, 5.35rem);
      place-items: center;
      overflow: hidden;
      border-radius: clamp(1.25rem, 4vw, 1.65rem);
      background: #8dd62c;
      box-shadow: 0 18px 42px rgba(141, 214, 44, .3);
      animation: mobileLoaderMark 1.8s ease-in-out infinite;
    }

    .crm-mobile-offline-loader .mobile-loading-logo {
      display: block;
      width: 100%;
      height: 100%;
      object-fit: cover;
    }

    .crm-mobile-offline-card {
      padding: 1.45rem;
      border: 1px solid rgba(207, 222, 195, .96);
      border-radius: 1.75rem;
      background:
        radial-gradient(circle at 88% 4%, rgba(141, 214, 44, .12), transparent 9rem),
        rgba(255, 255, 255, .94);
      box-shadow: 0 2rem 5.5rem rgba(31, 45, 61, .15), inset 0 1px 0 rgba(255, 255, 255, .96);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
    }

    .crm-mobile-offline-icon {
      display: grid;
      width: 4.35rem;
      height: 4.35rem;
      margin-bottom: 1.2rem;
      place-items: center;
      border: 1px solid rgba(141, 214, 44, .28);
      border-radius: 1.35rem;
      background: linear-gradient(145deg, #f4fde9, #fff);
      color: #67a81c;
      box-shadow: 0 1rem 2.4rem rgba(103, 168, 28, .14);
    }

    .crm-mobile-offline-icon svg {
      width: 2.1rem;
      height: 2.1rem;
      stroke: currentColor;
    }

    .crm-mobile-offline-card h1 {
      margin: 0 0 .42rem;
      color: #172033;
      font-size: clamp(1.72rem, 8vw, 2.08rem);
      font-weight: 950;
      letter-spacing: -.045em;
      line-height: 1.05;
    }

    .crm-mobile-offline-card h2 {
      margin: 0 0 .72rem;
      color: #2c3828;
      font-size: 1.12rem;
      font-weight: 850;
      line-height: 1.2;
    }

    .crm-mobile-offline-card p {
      margin: 0;
      color: #687164;
      font-size: .95rem;
      line-height: 1.55;
    }

    .crm-mobile-offline-retry {
      display: inline-flex;
      width: 100%;
      min-height: 3.25rem;
      align-items: center;
      justify-content: center;
      gap: .55rem;
      margin-top: 1.25rem;
      padding: .75rem 1rem;
      border: 1px solid #69a91f;
      border-radius: 1.05rem;
      background: linear-gradient(180deg, #7cc426, #69aa1f);
      color: #fff;
      font: inherit;
      font-size: .98rem;
      font-weight: 900;
      line-height: 1;
      box-shadow: 0 .9rem 1.9rem rgba(105, 170, 31, .24), inset 0 1px 0 rgba(255, 255, 255, .32);
      -webkit-tap-highlight-color: transparent;
      overflow: visible;
    }

    .crm-mobile-offline-retry svg {
      width: 1.08rem;
      height: 1.08rem;
      display: block;
      flex: 0 0 1.08rem;
      overflow: visible !important;
      fill: none !important;
      stroke: currentColor !important;
    }

    html.crm-offline-mobile-loading .crm-mobile-offline-loader {
      opacity: 1;
    }

    html.crm-offline-mobile-loading .crm-mobile-offline-card {
      opacity: 0;
      pointer-events: none;
      transform: translate(-50%, calc(-50% + 1rem)) scale(.97);
    }

    html.crm-offline-mobile-ready .crm-mobile-offline-loader {
      opacity: 0;
      pointer-events: none;
      transform: translate(-50%, calc(-50% - .8rem)) scale(.97);
    }

    html.crm-offline-mobile-ready .crm-mobile-offline-card {
      opacity: 1;
      transform: translate(-50%, -50%) scale(1);
    }

    @keyframes mobileLoaderSpin {
      to { transform: rotate(360deg); }
    }

    @keyframes mobileLoaderPulse {
      0%, 100% { transform: scale(.94); opacity: .34; }
      50% { transform: scale(1.04); opacity: .82; }
    }

    @keyframes mobileLoaderGlow {
      from { transform: scale(.9); opacity: .35; }
      to { transform: scale(1.12); opacity: .85; }
    }

    @keyframes mobileLoaderMark {
      0%, 100% { transform: translateY(0) scale(1); }
      50% { transform: translateY(-3px) scale(1.04); }
    }

    @keyframes siteLoaderCardIn {
      from { transform: translateY(1rem) scale(.97); opacity: 0; }
      to { transform: translateY(0) scale(1); opacity: 1; }
    }

    @media (prefers-reduced-motion: reduce) {
      .crm-mobile-offline-panel { transition-duration: .01ms; }
      .crm-mobile-offline-loader .mobile-loading-orbit::before { animation-duration: 1.8s; }
    }
  }
</style>`;

const MOBILE_OFFLINE_MARKUP = `<section id="crmMobileOfflineExperience" aria-live="polite" aria-label="Нет подключения к интернету">
  <div class="crm-mobile-offline-panel crm-mobile-offline-loader" role="status">
    <div class="site-page-loader-card">
      <div class="mobile-loading-orbit" aria-hidden="true">
        <span></span><span></span><span></span>
        <div class="mobile-loading-mark">
          <img class="mobile-loading-logo" src="/static/brand-logo.png" width="82" height="82" alt="">
        </div>
      </div>
    </div>
  </div>
  <div class="crm-mobile-offline-panel crm-mobile-offline-card">
    <div class="crm-mobile-offline-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.55a10.9 10.9 0 0 1 14.1 0"/><path d="M8.5 16a6.1 6.1 0 0 1 7 0"/><path d="M12 19.5h.01"/><path d="m3 3 18 18"/></svg>
    </div>
    <h1>Упссс…</h1>
    <h2>Нет интернета</h2>
    <p>Проверьте подключение к сети и попробуйте открыть приложение ещё раз.</p>
    <button class="crm-mobile-offline-retry" type="button">
      <svg viewBox="-1 -1 26 26" fill="none" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6v5h-5"/><path d="M20 11a8 8 0 1 0 1.2 5.7"/></svg>
      <span>Попробовать снова</span>
    </button>
  </div>
</section>`;

const OFFLINE_NOTICE_SCRIPT = `<script>(()=>{window.__CRM_OFFLINE_FALLBACK__=true;document.documentElement.classList.add("crm-offline-fallback");const mobile=window.matchMedia("(max-width: 767.98px)").matches;if(!mobile)return;const root=document.documentElement;root.classList.add("crm-offline-mobile-experience","crm-offline-mobile-loading");const mount=()=>{if(!document.getElementById("crmMobileOfflineExperience"))document.body.insertAdjacentHTML("beforeend",${JSON.stringify(MOBILE_OFFLINE_MARKUP)});document.querySelector(".crm-mobile-offline-retry")?.addEventListener("click",()=>window.location.reload());window.setTimeout(()=>{root.classList.remove("crm-offline-mobile-loading");root.classList.add("crm-offline-mobile-ready")},1150)};if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",mount,{once:true});else mount();window.addEventListener("online",()=>window.setTimeout(()=>window.location.reload(),250),{once:true})})();</script>`;
const OFFLINE_HTML = `<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
  <meta name="theme-color" content="#f9fbf5">
  <title>Передача</title>
  ${MOBILE_OFFLINE_STYLE}
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
  ${MOBILE_OFFLINE_MARKUP}
  <main class="offline-card">
    <div class="offline-logo">
      <img src="/static/brand-logo.png" width="96" height="96" alt="">
    </div>
    <h1>Не удается обновить</h1>
    <p>Нет интернета и сохраненной версии этой страницы тоже нет. Подключитесь к сети и попробуйте снова.</p>
  </main>
  ${OFFLINE_NOTICE_SCRIPT}
</body>
</html>`;

const withSearch = request => new Request(request.url, { method: 'GET', credentials: 'same-origin' });
const withoutSearch = request => {
  const url = new URL(request.url);
  return new Request(`${url.origin}${url.pathname}`, { method: 'GET', credentials: 'same-origin' });
};

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const staticCache = await caches.open(STATIC_CACHE);
    const pageCache = await caches.open(PAGE_CACHE);

    await Promise.allSettled([
      staticCache.addAll(STATIC_ASSETS),
      ...APP_SHELL_PAGES.map(async path => {
        const request = new Request(path, {
          method: 'GET',
          credentials: 'same-origin',
          cache: 'reload',
        });
        const response = await fetch(request);
        if (response && response.ok) await pageCache.put(path, response.clone());
      }),
    ]);
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys
      .filter(key => ![STATIC_CACHE, PAGE_CACHE, ...LEGACY_PAGE_CACHES].includes(key))
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
    const networkResponse = await fetchWithTimeout(requestWithSearch, 3500);
    if (networkResponse && networkResponse.ok) {
      cache.put(requestWithSearch, networkResponse.clone()).catch(() => {});
      cache.put(requestWithoutSearch, networkResponse.clone()).catch(() => {});
      return networkResponse;
    }
    throw new Error(`HTTP ${networkResponse?.status || 0}`);
  } catch (error) {
    const cached = await matchCachedPage(requestWithSearch, requestWithoutSearch);
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

async function matchCachedPage(requestWithSearch, requestWithoutSearch) {
  const cacheNames = [PAGE_CACHE, ...LEGACY_PAGE_CACHES];
  const pathname = new URL(requestWithoutSearch.url).pathname;
  const fallbackPaths = pathname === '/'
    ? ['/object', '/objects', '/login']
    : (pathname === '/object' ? ['/', '/objects', '/login'] : ['/login']);

  for (const cacheName of cacheNames) {
    const cache = await caches.open(cacheName);
    const exact = await cache.match(requestWithSearch) || await cache.match(requestWithoutSearch);
    if (exact) return exact;
    for (const fallbackPath of fallbackPaths) {
      const fallback = await cache.match(fallbackPath);
      if (fallback) return fallback;
    }
  }

  return caches.match('/login');
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
    const offlineHead = `${MOBILE_OFFLINE_STYLE}${OFFLINE_NOTICE_SCRIPT}`;
    html = html.includes('</head>')
      ? html.replace('</head>', `${offlineHead}</head>`)
      : `${offlineHead}${html}`;
  }

  headers.set('Content-Type', 'text/html; charset=utf-8');
  return new Response(html, {
    status: response.status || 200,
    statusText: response.statusText || 'OK',
    headers,
  });
}

async function fetchWithTimeout(request, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(request, { signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}
