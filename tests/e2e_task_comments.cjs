const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const { chromium } = require('playwright');

// Run against tests/e2e_visual_server.py, which uses a disposable seeded database.
(async () => {
  const browser = await chromium.launch({ headless: true });
  const base = process.env.E2E_VISUAL_BASE_URL || 'http://127.0.0.1:5098';
  const output = process.env.E2E_ARTIFACT_DIR || path.resolve(__dirname, '../_codex_chat_files/comments');
  fs.mkdirSync(output, { recursive: true });
  try {
    for (const profile of [
      { name: 'desktop-wide', viewport: { width: 1440, height: 1000 } },
      { name: 'desktop-narrow', viewport: { width: 1100, height: 900 } },
      { name: 'iphone-16-pro-max', viewport: { width: 440, height: 956 }, isMobile: true, hasTouch: true,
        deviceScaleFactor: 3, userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1' },
    ]) {
      const { name, ...options } = profile;
      const context = await browser.newContext(options);
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(`${base}/login`);
      await page.fill('[name=username]', 'e2e-admin');
      await page.fill('[name=password]', 'E2E-visual-password-2026!');
      await page.locator('.login-form').evaluate(form => { form.dataset.csrfReady = '1'; });
      await Promise.all([page.waitForURL(url => !url.pathname.startsWith('/login')), page.locator('.login-submit').click()]);
      await page.goto(`${base}/tasks/1`);
      const form = page.locator('[data-task-comment-async]');
      const textarea = form.locator('textarea');
      assert.equal(await form.locator('[type=reset]').count(), 0);
      const text = `Comment ${name} <script>alert(1)</script> ${'LongWord'.repeat(40)}`;
      const before = await page.locator('.comment-item').count();
      await textarea.fill(text);
      const add = form.locator('[type=submit]');
      await add.focus();
      await add.hover();
      await add.click();
      await page.waitForFunction(count => document.querySelectorAll('.comment-item').length === count + 1, before);
      await page.waitForFunction(() => document.querySelector('[data-task-comment-async] textarea').value === '');
      assert.equal(await page.locator('.comment-item').last().locator('.comment-body').textContent(), text);
      assert.ok((await page.locator('[data-task-history-list]').textContent()).includes('Добавлен новый комментарий'));
      assert.equal(await page.locator('.crm-toast-danger').count(), 0);
      const layout = await page.locator('.comment-item').last().evaluate(item => {
        const body = item.querySelector('.comment-body').getBoundingClientRect();
        const button = item.querySelector('[aria-label="Удалить комментарий"]');
        const rect = button.getBoundingClientRect();
        return { right: rect.x >= body.right, inside: rect.right <= item.getBoundingClientRect().right,
          icon: Boolean(button.querySelector('.bi-trash')), text: button.textContent.trim(), width: rect.width };
      });
      assert.ok(layout.right && layout.inside && layout.icon, `${name}: delete icon must be right of comment`);
      assert.equal(layout.text, '');
      assert.ok(layout.width <= 44, `${name}: delete button should be compact`);
      const overflow = await page.locator('.comment-item').last().evaluate(el => el.scrollWidth > el.clientWidth + 1);
      assert.equal(overflow, false, `${name}: comment overflow`);
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: false });
      await page.locator('.task-detail-comments-card').screenshot({ path: path.join(output, `${name}-card.png`) });
      // Newly appended forms must participate in the existing delegated confirmation dialog.
      await page.locator('.comment-item').last().getByRole('button', { name: 'Удалить комментарий' }).click();
      await page.locator('.js-crm-confirm-cancel').click();
      assert.equal(await page.locator('.comment-item').count(), before + 1);
      // Existing comments retain the delete action after reloading.
      await page.reload();
      await page.locator('.comment-item').last().getByRole('button', { name: 'Удалить комментарий' }).click();
      await Promise.all([page.waitForURL(`${base}/tasks/1`), page.locator('.js-crm-confirm-ok').click()]);
      await page.waitForFunction(count => document.querySelectorAll('.comment-item').length === count, before);
      await textarea.fill('Delete immediately after posting');
      await add.click();
      await page.waitForFunction(count => document.querySelectorAll('.comment-item').length === count + 1, before);
      await page.locator('.comment-item').last().getByRole('button', { name: 'Удалить комментарий' }).click();
      await page.locator('.js-crm-confirm-ok').click();
      await page.waitForFunction(count => document.querySelectorAll('.comment-item').length === count, before);
      // A rejected request must keep the draft and re-enable the controls.
      await page.route('**/tasks/1/comment', route => route.fulfill({ status: 500, contentType: 'application/json', body: '{"ok":false,"message":"Test failure"}' }));
      await textarea.fill('Keep draft after failure');
      await add.click();
      await page.waitForFunction(() => !document.querySelector('[data-task-comment-async] [type=submit]').disabled);
      assert.equal(await textarea.inputValue(), 'Keep draft after failure');
      assert.equal(await page.locator('.comment-item').count(), before);
      assert.deepEqual(errors, [], `${name}: browser errors`);
      console.log(`${name}: add, history, compact delete icon, escaping, overflow, cancel and delete passed`);
      await context.close();
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
