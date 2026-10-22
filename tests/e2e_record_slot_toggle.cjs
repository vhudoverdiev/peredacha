const assert = require('node:assert/strict');
const { chromium, webkit } = require('playwright');
const base = process.env.E2E_VISUAL_BASE_URL || 'http://127.0.0.1:5098';
(async () => {
  for (const [engine, width] of [['chromium', 1440], ['chromium', 1024], ['webkit', 440]]) {
    const browser = await (engine === 'webkit' ? webkit.launch() : chromium.launch({ executablePath: process.env.E2E_VISUAL_BROWSER_EXECUTABLE }));
    try {
      const context = await browser.newContext({ viewport: { width, height: 956 },
        isMobile: engine === 'webkit', hasTouch: engine === 'webkit', serviceWorkers: 'block',
        ...(engine === 'webkit' ? { userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1' } : {}) });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(base + '/login');
      await page.fill('[name=username]', 'e2e-developer');
      await page.fill('[name=password]', 'E2E-developer-password-2026!');
      await page.locator('.login-submit').click();
      await page.waitForURL(url => !url.pathname.startsWith('/login'));
      await page.goto(base + '/objects/1/open');
      await page.goto(base + '/records/availability');
      const csrf = await page.locator('input[name=csrf_token]').first().inputValue();
      const response = await context.request.post(base + '/records/availability', { form: {
        csrf_token: csrf, start_date: '2026-11-02', end_date: '2026-11-02',
        start_time: '14:00', end_time: '15:00', duration: '30', weekday: '0',
      }});
      assert.ok(response.ok());
      await page.goto(base + '/records?date=2026-11-02');
      await page.evaluate(() => { window.slotToggleDocument = 'unchanged'; });
      const first = page.locator('[data-record-slot]').first();
      const button = first.locator('[data-slot-toggle] button');
      await button.waitFor({ state: 'visible' });
      const box = await button.boundingBox();
      // Desktop CRM uses a fixed shell zoom; verify CSS size and rendered bounds.
      assert.ok(Math.abs(await button.evaluate(el => parseFloat(getComputedStyle(el).width)) - 40) < 0.1);
      const minimum = engine === 'webkit' ? 36 : 20;
      assert.ok(box.width >= minimum && box.width <= 48 && box.height >= minimum && box.height <= 48, JSON.stringify(box));
      assert.ok(box.x >= 0 && box.x + box.width <= width);
      if (engine === 'chromium') await button.hover();
      await button.focus();
      assert.equal(await button.getAttribute('aria-label'), 'Закрыть время');
      await button.click();
      await first.locator('[data-slot-toggle] button[aria-label="Открыть время"]').waitFor();
      assert.equal(await first.locator('[data-slot-book]').isVisible(), false);
      await button.click();
      await first.locator('[data-slot-toggle] button[aria-label="Закрыть время"]').waitFor();
      assert.equal(await first.locator('[data-slot-book]').isVisible(), true);
      assert.equal(await page.evaluate(() => window.slotToggleDocument), 'unchanged');
      // AJAX replacement must retain the delegated submit handler and icon state.
      await page.locator('[data-ajax-pagination-tabs] a').filter({ hasText: 'Неделя' }).click();
      await page.waitForFunction(() => document.querySelector('.records-page').dataset.recordsView === 'week');
      await page.locator('[data-slot-toggle] button[aria-label="Закрыть время"]').first().click();
      await page.locator('[data-slot-toggle] button[aria-label="Открыть время"]').first().click();
      await page.waitForFunction(() => !document.querySelector('[data-slot-toggle][data-pending="1"]'));
      assert.deepEqual(errors, []);
      console.log(`PASS slot close/open, icon layout and AJAX week: ${engine} ${width}`);
      await context.close();
    } finally { await browser.close(); }
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
