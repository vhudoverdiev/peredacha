const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium, webkit } = require('playwright');
const base = process.env.E2E_VISUAL_BASE_URL || 'http://127.0.0.1:5098';
(async () => {
  for (const engine of ['chromium', 'webkit']) {
    const browser = await (engine === 'webkit' ? webkit.launch() : chromium.launch({ executablePath: process.env.E2E_VISUAL_BROWSER_EXECUTABLE }));
    try {
      const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, serviceWorkers: 'block' });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(base + '/login');
      await page.fill('[name=username]', 'e2e-developer');
      await page.fill('[name=password]', 'E2E-developer-password-2026!');
      await page.locator('.login-submit').click();
      await page.waitForURL(url => !url.pathname.startsWith('/login'));
      await page.goto(base + '/objects/1/open');
      await page.goto(base + '/tasks/recognition');
      await page.goto(base + '/tasks');
      await page.goBack();
      await page.waitForURL('**/tasks/recognition');
      const form = page.locator('.task-recognition-upload-form');
      await form.locator('[name=pdf_files]').setInputFiles(path.resolve('_codex_chat_files/recognition-audit.pdf'));
      await form.locator('[name=csrf_token]').evaluate(input => { input.value = 'STALE_TOKEN_AFTER_BACK'; });
      let posts = 0;
      page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/tasks/recognition')) posts++; });
      await page.route('**/csrf-token', route => route.fulfill({ status: 503, contentType: 'application/json', body: '{}' }));
      await form.locator('[type=submit]').click();
      await page.waitForFunction(() => !document.querySelector('.task-recognition-upload-form [type=submit]').disabled);
      assert.equal(posts, 0);
      assert.equal(await form.locator('[name=pdf_files]').evaluate(input => input.files[0]?.name), 'recognition-audit.pdf');
      await page.unroute('**/csrf-token');
      const submitted = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith('/tasks/recognition'));
      await form.locator('[type=submit]').click();
      const response = await submitted;
      assert.equal(response.status(), 200);
      await page.waitForLoadState('load');
      assert.equal(posts, 1);
      assert.ok(!(await page.locator('input[name=csrf_token]').first().inputValue()).includes('STALE_TOKEN_AFTER_BACK'));
      await page.waitForTimeout(200);
      assert.equal(posts, 1, 'No POST replay after the response');
      assert.deepEqual(errors, []);
      console.log(`PASS CSRF after Back, refresh failure, one deliberate POST: ${engine}`);
      await context.close();
    } finally { await browser.close(); }
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
