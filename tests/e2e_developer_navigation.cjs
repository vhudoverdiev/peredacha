const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const { chromium } = require('playwright');

// Use the disposable database seeded by tests/e2e_visual_server.py.
(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.E2E_VISUAL_BROWSER_EXECUTABLE });
  const base = process.env.E2E_VISUAL_BASE_URL || 'http://127.0.0.1:5098';
  const output = process.env.E2E_ARTIFACT_DIR || path.resolve(__dirname, '../_codex_chat_files/developer-navigation');
  fs.mkdirSync(output, { recursive: true });
  const expected = ['Обращения', 'Логи удалений', 'Статистика', 'Обновления'];
  try {
    for (const width of [1440, 1100]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 } });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(`${base}/login`);
      await page.fill('[name=username]', 'e2e-developer');
      await page.fill('[name=password]', 'E2E-developer-password-2026!');
      await Promise.all([page.waitForURL(url => !url.pathname.startsWith('/login')), page.locator('.login-submit').click()]);
      await page.goto(`${base}/site-errors`);
      await page.waitForLoadState('networkidle');
      const tabs = page.locator('.developer-section-tabs');
      const links = tabs.locator('a');
      assert.deepEqual(await links.locator('span').allTextContents(), expected);
      const before = await links.evaluateAll(nodes => nodes.map(el => el.getBoundingClientRect().x));
      await links.nth(1).focus();
      await links.nth(1).hover();
      await links.nth(1).click();
      await page.waitForURL('**/developer/delete-logs');
      await tabs.locator('a.active').filter({ hasText: 'Логи удалений' }).waitFor();
      assert.deepEqual(await links.locator('span').allTextContents(), expected);
      const after = await links.evaluateAll(nodes => nodes.map(el => el.getBoundingClientRect().x));
      before.forEach((x, index) => assert.ok(Math.abs(x - after[index]) <= 1, `tab ${index} shifted at ${width}px`));
      assert.equal(await tabs.evaluate(el => el.scrollWidth > el.clientWidth + 1), false);
      await tabs.screenshot({ path: path.join(output, `tabs-${width}.png`) });
      await page.reload();
      assert.deepEqual(await links.locator('span').allTextContents(), expected);
      await links.nth(2).click();
      await page.waitForURL('**/developer/statistics?days=30');
      await tabs.locator('a.active').filter({ hasText: 'Статистика' }).waitFor();
      assert.deepEqual(await links.locator('span').allTextContents(), expected);
      await links.nth(0).click();
      await page.waitForURL('**/site-errors');
      await tabs.locator('a.active').filter({ hasText: 'Обращения' }).waitFor();
      assert.deepEqual(await links.locator('span').allTextContents(), expected);
      assert.deepEqual(errors, []);
      await page.goto(`${base}/site-errors`);
      await page.locator('.developer-section-tabs a').filter({hasText:'Обновления'}).click();
      await page.waitForURL('**/developer/updates');
      await page.getByRole('heading',{name:'Новое обновление',exact:true}).waitFor();
      assert.deepEqual(await page.locator('.developer-section-tabs a span').allTextContents(),expected);
      console.log(`${width}px: tab order, positions, active states, AJAX navigation and reload passed`);
      await context.close();
    }
    const mobile = await browser.newContext({ viewport: { width: 440, height: 956 }, isMobile: true, hasTouch: true,
      userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1' });
    const page = await mobile.newPage();
    await page.goto(`${base}/login`);
    await page.fill('[name=username]', 'e2e-developer');
    await page.fill('[name=password]', 'E2E-developer-password-2026!');
    await Promise.all([page.waitForURL(url => !url.pathname.startsWith('/login')), page.locator('.login-submit').click()]);
    await page.goto(`${base}/developer/delete-logs`);
    assert.ok(!new URL(page.url()).pathname.startsWith('/developer'));
    assert.equal(await page.locator('.developer-section-tabs').count(), 0);
    console.log('iPhone 16 Pro Max: existing mobile access restriction preserved');
    await mobile.close();
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
