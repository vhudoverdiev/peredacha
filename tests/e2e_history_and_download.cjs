const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium, webkit } = require('playwright');
const base = process.env.E2E_VISUAL_BASE_URL || 'http://127.0.0.1:5098';
(async () => {
  for (const engine of ['chromium', 'webkit']) {
    const browser = await (engine === 'webkit' ? webkit.launch() : chromium.launch({ executablePath: process.env.E2E_VISUAL_BROWSER_EXECUTABLE }));
    try {
      const context = await browser.newContext({ viewport: { width: engine === 'webkit' ? 440 : 1440, height: 956 },
        isMobile: engine === 'webkit', hasTouch: engine === 'webkit', acceptDownloads: true,
        userAgent: engine === 'webkit' ? 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1'
          : 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:140.0) Gecko/20100101 Firefox/140.0' });
      await context.addInitScript(() => window.addEventListener('unload', () => {}));
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(base + '/login');
      await page.fill('[name=username]', 'e2e-developer');
      await page.fill('[name=password]', 'E2E-developer-password-2026!');
      await page.locator('.login-submit').click();
      await page.waitForURL(url => !url.pathname.startsWith('/login'));
      await page.goto(base + '/objects/1/open');
      await page.goto(base + '/appeals/new');
      await page.locator('[name=body]').fill('Неотправленный текст — назад/вперёд');
      await page.locator('[name=caller_name]').fill('Проверка истории');
      await page.locator('[name=apartment_id]').selectOption({ index: 1 }, { force: true });
      const selected = await page.locator('[name=apartment_id]').inputValue();
      const token = await page.locator('form input[name=csrf_token]').first().inputValue();
      await page.evaluate(() => {
        for (const [type, name, value] of [['password', 'password', 'PRIVATE_PASSWORD_SENTINEL'], ['text', 'verification_code', 'PRIVATE_CODE_SENTINEL']]) {
          const input = document.createElement('input');
          Object.assign(input, { type, name, value });
          document.querySelector('form.workflow-editor').appendChild(input);
        }
        const form = document.createElement('form');
        form.id = 'history-autosave-fixture';
        form.dataset.apartmentDetailsAutosave = '1';
        document.body.appendChild(form);
        const input = document.createElement('input');
        input.name = 'auto_saved_value'; input.value = 'PRIVATE_AUTOSAVE_SENTINEL';
        input.setAttribute('form', form.id);
        document.body.appendChild(input);
      });
      await page.goto(base + '/records');
      await page.goBack();
      await page.waitForURL('**/appeals/new');
      await page.waitForTimeout(600);
      assert.equal(await page.locator('[name=body]').inputValue(), 'Неотправленный текст — назад/вперёд');
      assert.equal(await page.locator('[name=caller_name]').inputValue(), 'Проверка истории');
      assert.equal(await page.locator('[name=apartment_id]').inputValue(), selected);
      const saved = await page.evaluate(() => Object.keys(sessionStorage).filter(key => key.startsWith('crm-history-v1:') && key !== 'crm-history-v1:user').map(key => sessionStorage.getItem(key)).join(''));
      assert.ok(!saved.includes(token));
      assert.ok(!saved.includes('PRIVATE_PASSWORD_SENTINEL'));
      assert.ok(!saved.includes('PRIVATE_CODE_SENTINEL'));
      assert.ok(!saved.includes('PRIVATE_AUTOSAVE_SENTINEL'));
      assert.equal(await page.locator('.crm-firefox-navigation-frame').count(), 0);
      await page.goForward();
      await page.waitForURL('**/records');
      await page.goto(base + '/appeals?q=__history_filter__&status=required');
      await page.goto(base + '/records');
      await page.goBack();
      await page.waitForURL('**/appeals?*');
      await page.waitForTimeout(600);
      assert.equal(await page.locator('[name=q]').inputValue(), '__history_filter__');
      assert.equal(await page.locator('[name=status]').inputValue(), 'required');
      await page.goto(base + '/records');
      await page.locator('[data-ajax-pagination-tabs] a').filter({ hasText: 'Неделя' }).click();
      await page.waitForURL('**/records?*view=week*');
      await page.goBack();
      await page.waitForFunction(() => document.querySelector('.records-page').dataset.recordsView === 'day');
      await page.waitForTimeout(500);
      assert.equal(await page.locator('[data-ajax-pagination-tabs] .is-active').textContent(), 'День');
      await page.goForward();
      await page.waitForFunction(() => document.querySelector('.records-page').dataset.recordsView === 'week');
      // Real service-worker control, then generation taking longer than its HTML timeout.
      if (engine === 'chromium') {
        await page.goto(base + '/apartments/1');
        await page.evaluate(async () => {
          const registration = await navigator.serviceWorker.register('/service-worker.js');
          await navigator.serviceWorker.ready;
          return registration.scope;
        });
        await page.reload();
        await page.waitForFunction(() => !!navigator.serviceWorker.controller);
        const downloadUrl = '/apartments/1/source-table/export';
        await page.route('**' + downloadUrl, async route => {
          await new Promise(resolve => setTimeout(resolve, 4100));
          const response = await route.fetch();
          await route.fulfill({ response });
        });
        const urlBefore = page.url();
        const tableButton = page.locator('.apartment-source-export-btn');
        const initialBox = await tableButton.boundingBox();
        const initialMarkup = await tableButton.innerHTML();
        const started = Date.now();
        const download = page.waitForEvent('download', { timeout: 20000 });
        await tableButton.click();
        await page.waitForFunction(() => document.querySelector('.apartment-source-export-btn').classList.contains('is-loading'));
        const busyBox = await tableButton.boundingBox();
        assert.equal(busyBox.width, initialBox.width);
        assert.equal(busyBox.height, initialBox.height);
        assert.equal(await tableButton.innerHTML(), initialMarkup);
        const file = await download;
        assert.ok(Date.now() - started >= 4000);
        assert.ok(file.suggestedFilename().endsWith('.xlsx'));
        assert.equal(await file.failure(), null);
        await file.saveAs(path.join(process.env.E2E_ARTIFACT_DIR || '_codex_chat_files', 'premise-download-regression.xlsx'));
        assert.equal(page.url(), urlBefore);
        await page.waitForFunction(() => !document.querySelector('.apartment-source-export-btn').classList.contains('is-loading'));
        assert.equal(await page.locator('.crm-firefox-navigation-frame').count(), 0);
        assert.equal(await page.locator('[data-offline-screen]').count(), 0);
        await page.unroute('**' + downloadUrl);
        await page.route('**' + downloadUrl, route => route.fulfill({ status: 500,
          contentType: 'application/json', body: JSON.stringify({ ok: false, message: 'Тестовая ошибка выгрузки' }) }));
        const failed = page.waitForResponse(response => response.url().endsWith(downloadUrl));
        await page.locator('.apartment-source-export-btn').click();
        assert.equal((await failed).status(), 500);
        await page.waitForFunction(() => !document.querySelector('.apartment-source-export-btn').classList.contains('is-loading'));
        assert.equal(page.url(), urlBefore);
        await page.unroute('**' + downloadUrl);
        // An HTML response or redirect must never navigate CRM away from the card.
        for (const reply of [
          { status: 200, contentType: 'text/html', body: '<html>Not an Excel file</html>' },
          { status: 302, headers: { location: 'https://drive.google.com/' }, body: '' },
        ]) {
          await page.route('**' + downloadUrl, route => route.fulfill(reply));
          await tableButton.click();
          await page.waitForFunction(() => !document.querySelector('.apartment-source-export-btn').classList.contains('is-loading'));
          assert.equal(page.url(), urlBefore);
          assert.equal(await tableButton.innerHTML(), initialMarkup);
          assert.equal((await tableButton.boundingBox()).width, initialBox.width);
          await page.unroute('**' + downloadUrl);
        }
        const retry = page.waitForEvent('download');
        await page.locator('.apartment-source-export-btn').click();
        assert.equal(await (await retry).failure(), null);

      }
      assert.deepEqual(errors, []);
      await page.goto(base + '/account');
      if (engine === 'chromium') await page.locator('.objects-topbar .topbar-user').click();
      await page.locator('form[action="/logout"] button:visible').first().click();
      await page.waitForURL(url => url.pathname === '/login' || url.pathname === '/');
      await page.waitForFunction(() => !Object.keys(sessionStorage).some(key => key.startsWith('crm-history-v1:') && key !== 'crm-history-v1:user'));
      console.log(`PASS history, drafts, filters and downloads: ${engine}`);
      await context.close();
    } finally { await browser.close(); }
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
