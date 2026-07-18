const STATIC_CACHE = 'peredacha-static-v46-mobile-loader-edge-fix';
const STATIC_ASSETS = [
  '/static/site.webmanifest',
  '/static/brand-logo.png',
  '/static/apple-touch-icon.png',
  '/static/favicon-32x32.png',
  '/static/favicon-16x16.png',
  '/static/apple-splash.png',
  '/static/apple-splash-1290x2796.png',
  '/static/vendor/bootstrap/bootstrap.min.css?v=5.3.3',
  '/static/vendor/bootstrap/bootstrap-icons.min.css?v=1.11.3',
  '/static/vendor/bootstrap/bootstrap.bundle.min.js?v=5.3.3',
  '/static/vendor/bootstrap/fonts/bootstrap-icons.woff2',
  '/static/vendor/bootstrap/fonts/bootstrap-icons.woff',
  '/static/style.css?v=v612-mobile-loader-edge-fix',
  '/static/mobile-only.css?v=v39-mobile-loader-edge-fix',
  '/static/desktop-only.css?v=v19-desktop-layout-polish',
  '/static/script.js?v=v623-desktop-layout-polish',
];

const MOBILE_OFFLINE_HTML = `<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
  <meta name="theme-color" content="#f9fbf5">
  <title>Передача — нет интернета</title>
  <style>
    :root { color-scheme: light; background: #f9fbf5; }
    * { box-sizing: border-box; }
    html, body {
      width: 100%; min-height: 100%; margin: 0; overflow: hidden;
      background: #f9fbf5;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
      color: #172033;
    }
    .offline-screen {
      position: fixed; inset: 0; display: grid; place-items: center;
      width: 100vw; height: 100vh; height: 100lvh;
      padding: max(1.2rem, env(safe-area-inset-top)) 1.15rem max(1.2rem, env(safe-area-inset-bottom));
      background: #f9fbf5;
    }
    .offline-panel {
      position: absolute; left: 50%; top: 50%;
      width: min(calc(100% - 2.3rem), 25rem);
      transform: translate(-50%, -50%);
      transition: opacity .34s ease, transform .42s cubic-bezier(.2,.75,.24,1);
    }
    .offline-loader { display: grid; justify-items: center; }
    .mobile-standalone-boot-screen__orbit {
      position: relative; display: grid; width: 8rem; height: 8rem;
      min-width: 8rem; min-height: 8rem; max-width: 8rem; max-height: 8rem;
      place-items: center; flex: 0 0 8rem;
    }
    .mobile-standalone-boot-screen__ring,
    .mobile-standalone-boot-screen__glow {
      position: absolute; inset: 0; border-radius: 50%; pointer-events: none;
    }
    .mobile-standalone-boot-screen__ring { border: 2px solid transparent; }
    .mobile-standalone-boot-screen__ring--outer {
      border-top-color: rgba(141,214,44,.94); border-right-color: rgba(141,214,44,.2);
      animation: mobileStandaloneBootSpin 1.15s linear infinite;
    }
    .mobile-standalone-boot-screen__ring--inner {
      inset: .72rem; border-bottom-color: rgba(141,214,44,.88); border-left-color: rgba(141,214,44,.16);
      animation: mobileStandaloneBootSpin 1.55s linear infinite reverse;
    }
    .mobile-standalone-boot-screen__glow {
      inset: 1.65rem; background: radial-gradient(circle,rgba(141,214,44,.24),transparent 68%);
      animation: mobileStandaloneBootGlow 1.5s ease-in-out infinite alternate;
    }
    .mobile-standalone-boot-screen__mark {
      position: relative; z-index: 1; width: 5.15rem; height: 5.15rem;
      min-width: 5.15rem; min-height: 5.15rem; max-width: 5.15rem; max-height: 5.15rem;
      overflow: hidden; border-radius: 1.45rem;
      box-shadow: 0 0 0 1px rgba(141,214,44,.14), 0 20px 42px rgba(144,170,111,.2), 0 0 28px rgba(141,214,44,.14);
    }
    .mobile-standalone-boot-screen__mark img { display: block; width: 100%; height: 100%; object-fit: cover; }
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
    @keyframes mobileStandaloneBootSpin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
    @keyframes mobileStandaloneBootGlow { from { transform: scale(.92); opacity: .36; } to { transform: scale(1.08); opacity: .74; } }
  </style>
</head>
<body>
  <main class="offline-screen">
    <section class="offline-panel offline-loader" role="status" aria-label="Загрузка">
      <div class="mobile-standalone-boot-screen__orbit" aria-hidden="true">
        <span class="mobile-standalone-boot-screen__ring mobile-standalone-boot-screen__ring--outer"></span>
        <span class="mobile-standalone-boot-screen__ring mobile-standalone-boot-screen__ring--inner"></span>
        <span class="mobile-standalone-boot-screen__glow"></span>
        <div class="mobile-standalone-boot-screen__mark"><img src="/static/brand-logo.png" alt=""></div>
      </div>
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

  if (request.mode === 'navigate') {
    event.respondWith(mobileNavigationNetworkFirst(request));
    return;
  }

  if (!url.pathname.startsWith('/static/')) return;

  event.respondWith(staticNetworkFirst(request));
});

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
