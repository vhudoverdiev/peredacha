const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require('playwright');

// e2e_visual_server.py: E2E_WORKER_FIXTURES=1 E2E_VISUAL_CSRF_ENABLED=1.
const base = process.env.E2E_VISUAL_BASE_URL || 'http://127.0.0.1:5098';
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.E2E_VISUAL_BROWSER_EXECUTABLE });
  try {
    for (const role of ['painter', 'handyman', 'glazier']) {
      for (const width of [1440, 1100, 768, 440]) {
        const phone = width === 440;
        const context = await browser.newContext({ viewport: { width, height: 956 },
          isMobile: phone, hasTouch: phone, reducedMotion: 'reduce',
          ...(phone ? { deviceScaleFactor: 3, userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile/15E148 Safari/604.1' } : {}) });
        try {
          if (phone) await context.addInitScript(() => Object.defineProperty(navigator, 'standalone', { get: () => true }));
          const page = await context.newPage();
          const errors = [];
          page.on('pageerror', error => errors.push(error.message));
          await page.goto(`${base}/login`);
          await page.fill('[name=username]', `qa-${role}`);
          await page.fill('[name=password]', 'Worker-qa-password-2026!');
          await Promise.all([page.waitForURL('**/my-tasks'), page.locator('.login-submit').click()]);
          await page.locator(phone ? '.mobile-worker-bottom-nav a[href="/my-inspections"]' : '.worker-section-nav a[href="/my-inspections"]').click();
          await page.waitForURL('**/my-inspections');
          assert.equal(await page.locator('[data-worker-inspection-project]').count(), 2);
          assert.equal(await page.locator('[data-worker-inspection]').count(), 2);
          assert.deepEqual(await page.locator('.worker-inspection-card time').allTextContents(), ['09:15', '10:00']);
          const text = await page.locator('.worker-inspections-page').textContent();
          assert.ok(!text.includes('Недоступный объект'));
          assert.ok(!text.includes('999'));
          assert.ok(!text.includes('12:00'));
          assert.ok(!text.includes('Личные данные собственника'));
          assert.ok(!text.includes('+79991112233'));
          assert.equal(await page.locator('.worker-inspections-page form').count(), 0);
          assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
          if (phone) {
            assert.equal(await page.locator('.mobile-worker-bottom-nav a').count(), 3);
            const activeStyle = await page.locator('.mobile-worker-bottom-nav .active').evaluate(link => ({
              background: getComputedStyle(link).backgroundColor,
              color: getComputedStyle(link).color,
              icon: getComputedStyle(link.querySelector('i')).webkitTextFillColor,
              text: getComputedStyle(link.querySelector('span')).webkitTextFillColor,
            }));
            assert.deepEqual(activeStyle, { background: 'rgba(0, 0, 0, 0)', color: 'rgb(141, 214, 44)', icon: 'rgb(141, 214, 44)', text: 'rgb(141, 214, 44)' });
            const boxes = await page.locator('.mobile-worker-bottom-nav a').evaluateAll(links => links.map(link => {
              const rect = link.getBoundingClientRect(); return [rect.x, rect.width];
            }));
            assert.ok(boxes.every(([x, w]) => x >= 0 && x + w <= 441));
            assert.ok(boxes[1][0] >= boxes[0][0] + boxes[0][1] - 1);
          }
          if (process.env.E2E_ARTIFACT_DIR) await page.screenshot({ path: path.join(process.env.E2E_ARTIFACT_DIR, `worker-inspections-${role}-${width}.png`) });
          // The account menu must remain in the header, not move to a second grid row.
          if (!phone) {
            const geometry = await page.locator('.app-topbar').evaluate(header => {
              const account = header.querySelector('.topbar-user').getBoundingClientRect();
              const nav = header.querySelector('.worker-section-nav').getBoundingClientRect();
              const box = header.getBoundingClientRect();
              return { visible: account.x >= 0 && account.right <= innerWidth && account.top >= box.top && account.bottom <= box.bottom,
                separate: nav.right <= account.left, sameRow: Math.abs(nav.top + nav.height / 2 - account.top - account.height / 2) < 5 };
            });
            assert.ok(geometry.visible && geometry.separate && geometry.sameRow, JSON.stringify(geometry));
            await page.locator('.app-topbar .topbar-user').click();
          } else {
            await page.locator('.mobile-worker-bottom-nav a[href="/account"]').click();
            await page.waitForURL('**/account');
            await page.setViewportSize({ width: 440, height: 740 });
            await page.mouse.move(220, 400);
            await page.mouse.wheel(0, 600);
            await page.waitForTimeout(200);
            const scroll = await page.evaluate(() => ({ y: scrollY || document.body.scrollTop,
              bottom: document.querySelector('.mobile-worker-bottom-nav').getBoundingClientRect().bottom,
              position: getComputedStyle(document.querySelector('.mobile-worker-bottom-nav')).position }));
            assert.ok(scroll.y > 0, JSON.stringify(scroll));
            assert.equal(scroll.position, 'fixed');
            assert.ok(Math.abs(scroll.bottom - 740) < 2, JSON.stringify(scroll));
            await page.mouse.wheel(0, 10000);
            await page.waitForTimeout(200);
            const end = await page.evaluate(() => ({
              cardBottom: document.querySelector('.account-card:last-child').getBoundingClientRect().bottom,
              dockTop: document.querySelector('.mobile-worker-bottom-nav').getBoundingClientRect().top,
              padding: parseFloat(getComputedStyle(document.querySelector('.documents-content')).paddingBottom),
            }));
            assert.ok(end.cardBottom <= end.dockTop - 8, JSON.stringify(end));
            assert.ok(end.padding >= 84, JSON.stringify(end));
            if (process.env.E2E_ARTIFACT_DIR) await page.screenshot({ path: path.join(process.env.E2E_ARTIFACT_DIR, `worker-account-bottom-${role}.png`) });
          }
          const logout = page.locator('form[action="/logout"] button:visible').first();
          await logout.waitFor({ state: 'visible' });
          await logout.click();
          await page.waitForURL(url => url.pathname === '/login' || url.pathname === '/');
          assert.deepEqual(errors, []);
          console.log(`PASS worker daily inspections: ${role} ${width}`);
        } finally { await context.close(); }
      }
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
