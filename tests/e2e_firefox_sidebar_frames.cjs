/** Regression: sample every animation frame, not just the destination page.
 * Run against the disposable tests/e2e_visual_server.py on port 5098.
 */
const assert = require('node:assert/strict');
const { firefox, chromium } = require('playwright');
const base = process.env.E2E_BASE_URL || 'http://127.0.0.1:5098';

async function installProbe(page) {
  await page.evaluate(() => {
    window.__sidebarFrames = [];
    window.__sidebarDetachments = [];
    new window.__NativeMutationObserver(records => {
      for (const record of records) for (const node of record.removedNodes) {
        if (node.nodeType === 1 && (node.matches('.app-sidebar') || node.querySelector('.app-sidebar'))) {
          window.__sidebarDetachments.push(node.className);
        }
      }
    }).observe(document.body, {childList: true, subtree: true});
    window.__sidebarProbeRunning = true;
    const sample = () => {
      if (!window.__sidebarProbeRunning) return;
      const sidebar = document.querySelector('.app-sidebar');
      if (document.documentElement.classList.contains('desktop-shell-with-sidebar')) {
        const rect = sidebar?.getBoundingClientRect();
        let opacity = 1;
        for (let node = sidebar; node; node = node.parentElement) {
          const style = getComputedStyle(node);
          opacity *= Number(style.opacity);
          if (style.visibility === 'hidden' || style.display === 'none') opacity = 0;
        }
        const hit = rect && document.elementFromPoint(Math.min(30, rect.width / 2), 300);
        const background = sidebar && getComputedStyle(sidebar).backgroundColor;
        window.__sidebarFrames.push({
          time: performance.now(), path: location.pathname,
          valid: Boolean(sidebar && rect.width > 100 && rect.left <= 1 &&
            rect.bottom >= innerHeight - 2 && opacity >= 0.99 &&
            (hit === sidebar || sidebar.contains(hit)) &&
            background !== 'rgba(0, 0, 0, 0)' && background !== 'rgb(255, 255, 255)'),
          opacity, background, rect: rect?.toJSON(), hit: hit?.className,
        });
      }
      requestAnimationFrame(sample);
    };
    requestAnimationFrame(sample);
  });
}
async function settleFrames(page) {
  await page.evaluate(() => new Promise(resolve => {
    let remaining = 20;
    const frame = () => --remaining ? requestAnimationFrame(frame) : resolve();
    requestAnimationFrame(frame);
  }));
}
(async () => {
  for (const engine of ['firefox', 'chromium']) {
  const browser = await ({firefox,chromium}[engine].launch(engine === 'chromium' ? {executablePath: process.env.E2E_VISUAL_BROWSER_EXECUTABLE} : {}));
  try {
    for (const width of [1440, 1100]) {
      const page = await browser.newPage({ viewport: { width, height: 956 }, serviceWorkers: 'block' });
      await page.addInitScript(() => { window.__NativeMutationObserver = window.MutationObserver; });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(base + '/login');
      await page.fill('[name=username]', 'e2e-developer');
      await page.fill('[name=password]', 'E2E-developer-password-2026!');
      await page.locator('.login-submit').click();
      await page.waitForURL(url => !url.pathname.startsWith('/login'));
      await page.goto(base + '/objects');
      await installProbe(page);
      await page.evaluate(() => { window.__documentSentinel = 42; });
      let documentRequests = 0;
      page.on('request', request => {
        if (request.isNavigationRequest() && request.frame() === page.mainFrame()) documentRequests++;
      });
      await page.locator('.object-card[data-href="/objects/1/open"]').first().click();
      await page.waitForURL(base + '/');
      await page.waitForFunction(() => window.crmPageLoading === false);
      await settleFrames(page);
      const sidebar = await page.locator('.app-sidebar').elementHandle();
      for (const href of ['/tasks', '/apartments', '/records', '/appeals', '/']) {
        // A delayed response must leave the current sidebar visible too.
        await page.route(base + href, async route => {
          await new Promise(resolve => setTimeout(resolve, 180));
          await route.continue();
        }, { times: 1 });
        await page.evaluate(href => window.crmNavigate(href), href);
        await settleFrames(page);
        assert.equal(await sidebar.evaluate(node => node === document.querySelector('.app-sidebar')), true);
      }
      const frames = await page.evaluate(() => window.__sidebarFrames);
      assert.ok(frames.length >= 100, `Insufficient intermediate frames: ${frames.length}`);
      assert.deepEqual(frames.filter(frame => !frame.valid), [], 'Sidebar disappeared or exposed a white/transparent background');
      assert.equal(await page.evaluate(() => window.__documentSentinel), 42);
      assert.deepEqual(await page.evaluate(() => window.__sidebarDetachments), [], 'Sidebar or its ancestor was detached during navigation');
      assert.equal(documentRequests, 0, 'Unexpected full-document navigation');
      assert.deepEqual(errors, []);
      // Negative control: prove the probe detects a single hidden frame.
      await page.locator('.app-sidebar').evaluate(node => node.style.setProperty('opacity', '0', 'important'));
      await settleFrames(page);
      assert.ok(await page.evaluate(() => window.__sidebarFrames.some(frame => !frame.valid)), 'Probe failed to detect hidden sidebar');
      await page.locator('.app-sidebar').evaluate(node => node.style.removeProperty('opacity'));
      await page.evaluate(() => { window.__sidebarProbeRunning = false; });
      console.log(`PASS ${engine} ${width}px: ${frames.length} intermediate frames; object entry, delayed navigation, retained sidebar, negative control`);
      await page.close();
    }
  } finally { await browser.close(); }
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
