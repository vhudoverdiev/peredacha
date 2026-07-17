const STATIC_CACHE = 'peredacha-static-v10-solid-mobile-offline';
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

const MOBILE_OFFLINE_HTML = `<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
  <meta name="theme-color" content="#f4f8ee">
  <title>Передача — нет интернета</title>
  <style>
    :root { color-scheme: light; background: #f4f8ee; }
    * { box-sizing: border-box; }
    html, body {
      width: 100%; min-height: 100%; margin: 0; overflow: hidden;
      background: #f4f8ee;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
      color: #172033;
    }
    .offline-screen {
      position: fixed; inset: 0; display: grid; place-items: center;
      width: 100vw; height: 100vh; height: 100dvh;
      padding: max(1.2rem, env(safe-area-inset-top)) 1.15rem max(1.2rem, env(safe-area-inset-bottom));
      background: #f4f8ee;
    }
    .offline-panel {
      position: absolute; left: 50%; top: 50%;
      width: min(calc(100% - 2.3rem), 25rem);
      transform: translate(-50%, -50%);
      transition: opacity .34s ease, transform .42s cubic-bezier(.2,.75,.24,1);
    }
    .offline-loader { display: grid; justify-items: center; }
    .loader-card {
      display: grid; width: min(64vw, 19.5rem); min-width: 15rem; aspect-ratio: 1;
      place-items: center; border: 1px solid rgba(210,224,199,.92);
      border-radius: clamp(2rem,7vw,3.5rem); background: rgba(255,255,255,.88);
      box-shadow: 0 34px 95px rgba(31,45,61,.16);
    }
    .loading-orbit { position: relative; display: grid; width: clamp(8.5rem,30vw,11rem); height: clamp(8.5rem,30vw,11rem); place-items: center; }
    .loading-orbit::before, .loading-orbit::after, .loading-orbit > span {
      content: ""; position: absolute; inset: 0; border: 2px solid transparent; border-radius: 50%;
    }
    .loading-orbit::before { border-top-color: rgba(141,214,44,.92); border-right-color: rgba(141,214,44,.24); animation: spin 1.15s linear infinite; }
    .loading-orbit::after { inset: .75rem; border-bottom-color: rgba(141,214,44,.9); border-left-color: rgba(141,214,44,.22); animation: spin 1.7s linear infinite reverse; }
    .loading-orbit > span:nth-child(1) { inset: 1.55rem; border-top-color: rgba(124,58,237,.42); animation: pulse 1.6s ease-in-out infinite; }
    .loading-orbit > span:nth-child(2) { inset: -.35rem; border-right-color: rgba(141,214,44,.18); animation: pulse 1.9s ease-in-out infinite .18s; }
    .loading-orbit > span:nth-child(3) { inset: 2.25rem; background: rgba(141,214,44,.08); animation: glow 1.45s ease-in-out infinite alternate; }
    .loading-mark {
      z-index: 1; display: grid; width: clamp(4.2rem,15vw,5.35rem); height: clamp(4.2rem,15vw,5.35rem);
      place-items: center; overflow: hidden; border-radius: clamp(1.25rem,4vw,1.65rem);
      background: #8dd62c; box-shadow: 0 18px 42px rgba(141,214,44,.3);
    }
    .loading-mark img { display: block; width: 100%; height: 100%; object-fit: cover; }
    .offline-card {
      padding: 1.45rem; border: 1px solid rgba(207,222,195,.96); border-radius: 1.75rem;
      background: rgba(255,255,255,.96); box-shadow: 0 2rem 5.5rem rgba(31,45,61,.14);
    }
    .offline-icon {
      display: grid; width: 4.35rem; height: 4.35rem; margin-bottom: 1.2rem; place-items: center;
      border: 1px solid rgba(141,214,44,.28); border-radius: 1.35rem;
      background: #fff; color: #67a81c; box-shadow: 0 1rem 2.4rem rgba(103,168,28,.12);
    }
    .offline-icon svg { display: block; width: 2.1rem; height: 2.1rem; fill: none; stroke: currentColor; }
    h1 { margin: 0 0 .42rem; font-size: clamp(1.72rem,8vw,2.08rem); font-weight: 950; letter-spacing: -.045em; line-height: 1.05; }
    h2 { margin: 0 0 .72rem; color: #2c3828; font-size: 1.12rem; font-weight: 850; line-height: 1.2; }
    p { margin: 0; color: #687164; font-size: .95rem; line-height: 1.55; }
    .retry {
      display: inline-flex; width: 100%; min-height: 3.25rem; align-items: center; justify-content: center;
      gap: .55rem; margin-top: 1.25rem; padding: .75rem 1rem; overflow: visible;
      border: 1px solid #69a91f; border-radius: 1.05rem; background: #72b921; color: #fff;
      font: inherit; font-size: .98rem; font-weight: 900; line-height: 1;
      box-shadow: 0 .9rem 1.9rem rgba(105,170,31,.22);
    }
    .retry svg { display: block; width: 1.12rem; height: 1.12rem; flex: 0 0 1.12rem; overflow: visible; fill: none; stroke: currentColor; }
    html.loading .offline-card { opacity: 0; pointer-events: none; transform: translate(-50%,calc(-50% + 1rem)) scale(.97); }
    html.ready .offline-loader { opacity: 0; pointer-events: none; transform: translate(-50%,calc(-50% - .8rem)) scale(.97); }
    html.ready .offline-card { opacity: 1; transform: translate(-50%,-50%) scale(1); }
    @keyframes spin { to { transform: rotate(360deg); } }
    @keyframes pulse { 0%,100% { transform: scale(.94); opacity: .34; } 50% { transform: scale(1.04); opacity: .82; } }
    @keyframes glow { from { transform: scale(.9); opacity: .35; } to { transform: scale(1.12); opacity: .85; } }
  </style>
</head>
<body>
  <main class="offline-screen">
    <section class="offline-panel offline-loader" role="status" aria-label="Загрузка">
      <div class="loader-card"><div class="loading-orbit"><span></span><span></span><span></span><div class="loading-mark"><img src="/static/brand-logo.png" alt=""></div></div></div>
    </section>
    <section class="offline-panel offline-card" aria-live="polite">
      <div class="offline-icon" aria-hidden="true"><svg viewBox="0 0 24 24" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.55a10.9 10.9 0 0 1 14.1 0"/><path d="M8.5 16a6.1 6.1 0 0 1 7 0"/><path d="M12 19.5h.01"/><path d="m3 3 18 18"/></svg></div>
      <h1>Упссс…</h1><h2>Нет интернета</h2>
      <p>Проверьте подключение к сети и попробуйте открыть приложение ещё раз.</p>
      <button class="retry" type="button" onclick="location.reload()"><svg viewBox="-1 -1 26 26" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6v5h-5"/><path d="M20 11a8 8 0 1 0 1.2 5.7"/></svg><span>Попробовать снова</span></button>
    </section>
  </main>
  <script>setTimeout(()=>{document.documentElement.classList.remove('loading');document.documentElement.classList.add('ready')},1150);document.documentElement.classList.add('loading');addEventListener('online',()=>setTimeout(()=>location.reload(),250),{once:true});</script>
</body>
</html>`;

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
  if (url.origin !== self.location.origin) return;

  if (request.mode === 'navigate' && isMobileRequest(request)) {
    event.respondWith(mobileNavigationNetworkFirst(request));
    return;
  }

  if (!url.pathname.startsWith('/static/')) return;

  event.respondWith(staticNetworkFirst(request));
});

function isMobileRequest(request) {
  return /Android|iPhone|iPad|iPod|Mobile/i.test(request.headers.get('user-agent') || '');
}

async function mobileNavigationNetworkFirst(request) {
  try {
    return await fetch(request);
  } catch (error) {
    return new Response(MOBILE_OFFLINE_HTML, {
      status: 503,
      headers: {
        'Content-Type': 'text/html; charset=utf-8',
        'Cache-Control': 'no-store',
        'X-CRM-Mobile-Offline': '1',
      },
    });
  }
}

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
