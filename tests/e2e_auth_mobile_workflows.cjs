const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require('playwright');

// Run against e2e_visual_server.py with E2E_VISUAL_CSRF_ENABLED=1.
const base = process.env.E2E_VISUAL_BASE_URL || 'http://127.0.0.1:5098';
const artifactDir = process.env.E2E_ARTIFACT_DIR;
const phoneAgent = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1';

async function assertVisibilityControlBlack(control) {
  for (const state of ['normal', 'hover', 'focus', 'active']) {
    if (state === 'hover') await control.hover();
    if (state === 'focus') await control.focus();
    if (state === 'active') await control.evaluate(element => element.classList.add('active'));
    const colors = await control.evaluate(element => [element, ...element.querySelectorAll('i, span')]
      .map(node => [getComputedStyle(node).color, getComputedStyle(node).webkitTextFillColor]));
    assert.ok(colors.every(pair => pair.every(color => color === 'rgb(0, 0, 0)')), JSON.stringify({ state, colors }));
  }
}

async function login(page) {
  await page.goto(`${base}/login`);
  assert.equal(await page.locator('.login-form input[name=csrf_token]').count(), 1, 'Enable CSRF in the test server');
  await page.fill('[name=username]', 'e2e-developer');
  await page.fill('[name=password]', 'E2E-developer-password-2026!');
  await page.check('[name=remember]');
  await Promise.all([
    page.waitForURL(url => !url.pathname.startsWith('/login')),
    page.locator('.login-submit').click(),
  ]);
}

async function screenshot(page, name) {
  if (artifactDir) await page.screenshot({ path: path.join(artifactDir, `${name}.png`) });
}

async function shortcutStyle(page, selector) {
  return page.locator(selector).first().evaluate(element => {
    const style = getComputedStyle(element);
    const icon = getComputedStyle(element.querySelector('.mobile-section-shortcut-icon'));
    return Object.fromEntries([
      ...['borderRadius', 'backgroundImage', 'fontSize', 'fontWeight', 'minHeight'].map(key => [key, style[key]]),
      ['iconBackground', icon.backgroundImage],
    ]);
  });
}

async function run(browser, width, standalone = false) {
  const phone = width < 768;
  const label = `${width}${standalone ? '-pwa' : ''}`;
  const context = await browser.newContext({
    viewport: { width, height: 956 }, isMobile: phone, hasTouch: phone,
    ...(phone ? { userAgent: phoneAgent, deviceScaleFactor: 3 } : {}),
    reducedMotion: 'reduce',
  });
  try {
    if (standalone) await context.addInitScript(() => {
      Object.defineProperty(navigator, 'standalone', { get: () => true });
      Object.defineProperty(window, 'innerHeight', { get: () => 895 });
    });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await login(page);
    await page.goto(`${base}/objects/1/open`);

    // An existing selected object must not leak its actions into the chooser.
    await page.goto(`${base}/objects`);
    assert.equal(await page.locator('.workflow-mobile-shortcuts').count(), 0);
    await screenshot(page, `objects-${label}`);

    await page.goto(`${base}/`);
    const shortcuts = page.locator('.workflow-mobile-shortcuts');
    assert.equal(await shortcuts.isVisible(), phone);
    let referenceGap;
    if (phone) {
      assert.equal(await shortcuts.locator('a').count(), 2);
      const shortcutBoxes = await shortcuts.locator('a').evaluateAll(links => links.map(link => { const r = link.getBoundingClientRect(); return { top: r.top, right: r.right }; }));
      assert.ok(Math.abs(shortcutBoxes[0].top - shortcutBoxes[1].top) < 2);
      assert.ok(await shortcuts.locator('a > span').first().evaluate(element => element.scrollWidth <= element.clientWidth + 1));
      const workflowStyle = await shortcutStyle(page, '.workflow-mobile-shortcuts a');
      await page.locator('.workflow-mobile-shortcuts a').first().focus();
      assert.notEqual(await page.locator('.workflow-mobile-shortcuts a').first().evaluate(el => getComputedStyle(el).outlineStyle), 'none');
      await screenshot(page, `dashboard-${label}`);
      await Promise.all([
        page.waitForURL(url => url.pathname === '/appeals'),
        shortcuts.locator('a[href="/appeals"]').click(),
      ]);
      await page.goto(`${base}/`);
      await Promise.all([
        page.waitForURL(url => url.pathname === '/records'),
        page.locator('.workflow-mobile-shortcuts a[href="/records"]').click(),
      ]);
      await page.goto(`${base}/tasks`);
      assert.deepEqual(await shortcutStyle(page, '.remarks-measurements-mobile-btn'), workflowStyle);
      referenceGap = await page.evaluate(() => document.querySelector('.remarks-page-head').getBoundingClientRect().top
        - document.querySelector('.mobile-project-topbar').getBoundingClientRect().bottom);
      assert.ok(referenceGap >= 8 && referenceGap <= 28, `Reference header gap: ${referenceGap}`);
    }

    const routes = ['/appeals?q=__empty_call_test__', '/appeals', '/appeals/new', '/records', '/records?view=week', '/records?view=month'];
    routes.push('/records/availability');
    for (const route of routes) {
      const response = await page.goto(base + route);
      assert.equal(response.status(), 200, route);
      await page.evaluate(() => document.fonts.ready);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Overflow: ${route} ${label}`);
      if (phone) {
        const gap = await page.evaluate(() => document.querySelector('.workflow-page').getBoundingClientRect().top
          - document.querySelector('.mobile-project-topbar').getBoundingClientRect().bottom);
        assert.ok(Math.abs(gap - referenceGap) <= 1, `${route} header gap: ${gap}, reference: ${referenceGap}`);
      }
      if (phone) {
        const dock = await page.locator('.mobile-bottom-nav').evaluate(element => {
          const box = element.getBoundingClientRect();
          return { position: getComputedStyle(element).position, height: box.height, bottom: box.bottom };
        });
        assert.equal(dock.position, 'fixed', route);
        assert.equal(dock.height, 72, route);
        assert.ok(Math.abs(dock.bottom - 956) < 2, `${route} ${JSON.stringify(dock)}`);
        if (route.startsWith('/appeals?') || route === '/appeals' || route.startsWith('/records?') || route === '/records')
          assert.equal(await page.locator('.workflow-heading-copy').isVisible(), false);
        if (route === '/appeals') {
          await page.getByRole('link', { name: 'Назад', exact: true }).click();
          await page.waitForURL(url => url.pathname === '/');
          await page.goto(base + route);
        }
        if (standalone) {
          const anchor = await page.locator('.mobile-bottom-nav').evaluate(element => ({ top: getComputedStyle(element).top, bottom: getComputedStyle(element).bottom }));
          assert.equal(anchor.top, '884px');
          await page.mouse.move(220, 400);
          await page.mouse.wheel(0, 500);
          await page.waitForTimeout(100);
          assert.ok(Math.abs((await page.locator('.mobile-bottom-nav').boundingBox()).y - 884) < 2);
          await page.evaluate(() => { window.scrollTo(0, 0); document.body.scrollTop = 0; });
        }
        if (route === '/appeals/new') {
          assert.equal(await page.locator('.appeal-form-title').isVisible(), false);
          await page.getByRole('link', { name: 'Назад', exact: true }).click();
          await page.waitForURL('**/appeals');
          await page.goto(base + route);
        }
        if (route === '/records') {
          for (const name of ['Обзвонить', 'Скачать']) {
            assert.equal(await page.getByRole('link', { name, exact: true, includeHidden: true }).isVisible(), false);
          }
          const back = page.getByRole('link', { name: 'Назад', exact: true });
          await back.click();
          await page.waitForURL(url => url.pathname === '/');
          await page.goto(base + route);
          const action = page.getByRole('link', { name: 'Настроить время', exact: true });
          await action.focus();
          assert.equal(await action.evaluate(element => getComputedStyle(element, '::after').content), '"Настроить время"');
          assert.equal(await page.locator('.records-action-label').first().isVisible(), false);
        }
      }
      await screenshot(page, `${route.includes('appeals') ? 'appeals' : 'records'}-${label}-${route.includes('?') ? route.split('=')[1] : route.endsWith('new') ? 'new' : route.endsWith('availability') ? 'availability' : 'list'}`);
    }

    // The interval modal must stay inside the viewport and dismiss with Escape.
    await page.goto(`${base}/records`);
    await page.evaluate(() => {
      window.recordsDocumentToken = 'mounted';
      window.recordsMountedHeader = document.querySelector('.records-page > .workflow-head');
      window.recordsMountedTabs = document.querySelector('.workflow-view-switch');
    });
    for (const [view, text] of [['week', 'Неделя'], ['month', 'Месяц'], ['day', 'День']]) {
      await page.locator('.workflow-view-switch a').filter({ hasText: text }).click();
      await page.waitForFunction(expected => {
        const root = document.querySelector('.records-page');
        return root?.dataset.recordsView === expected && !root.hasAttribute('aria-busy');
      }, view);
      assert.ok(await page.evaluate(() => window.recordsDocumentToken === 'mounted'
        && window.recordsMountedHeader === document.querySelector('.records-page > .workflow-head')
        && window.recordsMountedTabs === document.querySelector('.workflow-view-switch')));
      assert.ok(await page.locator(`.workflow-calendar-${view}`).isVisible());
      assert.equal(await page.locator('.workflow-date-filter').isVisible(), view === 'day');
    }
    await page.goBack();
    await page.waitForFunction(() => document.querySelector('.records-page')?.dataset.recordsView === 'month');
    await page.goForward();
    await page.waitForFunction(() => document.querySelector('.records-page')?.dataset.recordsView === 'day'
      && !document.querySelector('.records-page').hasAttribute('aria-busy'));
    const stableUrl = page.url();
    await page.route('**/records?**', route => route.request().headers()['x-crm-partial-navigation'] === '1'
      ? route.abort() : route.continue());
    await page.locator('.workflow-view-switch a').filter({ hasText: 'Неделя' }).click();
    await page.waitForFunction(() => !document.querySelector('.records-page').hasAttribute('aria-busy'));
    assert.equal(page.url(), stableUrl);
    assert.equal(await page.evaluate(() => window.recordsDocumentToken), 'mounted');
    assert.ok(await page.locator('.workflow-calendar-day').isVisible());
    await page.unroute('**/records?**');

    const modalTrigger = page.locator('[data-close-interval-open]');
    if (await modalTrigger.count()) {
      await modalTrigger.click();
      const modal = page.locator('.workflow-interval-modal');
      assert.ok(await modal.isVisible());
      const box = await modal.boundingBox();
      assert.ok(box.x >= 0 && box.x + box.width <= width + 1);
      await page.keyboard.press('Escape');
      assert.equal(await modal.isVisible(), false);
    }

    await page.goto(`${base}/apartments/1`);
    assert.equal(await page.locator('.apartment-source-export-btn').isVisible(), !phone);
    const construction = page.locator('input[name=construction_number]');
    const newNumber = `C-001-${label}`;
    await construction.fill(newNumber);
    const saved = page.waitForResponse(response => response.url().endsWith('/apartments/1/details')
      && response.request().method() === 'POST');
    await construction.blur();
    assert.equal((await saved).status(), 200);
    await page.reload();
    assert.equal(await page.locator('input[name=construction_number]').inputValue(), newNumber);
    assert.ok((await page.locator('[data-apartment-history-card]').textContent()).includes('Строительный номер изменён'));
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Apartment overflow: ${label}`);
    await screenshot(page, `construction-number-${label}`);

    await page.goto(`${base}/records/call-list`);
    const numbers = await page.locator('.call-list-card h2').allTextContents();
    const values = numbers.map(value => Number(value.match(/\d+/)[0]));
    assert.deepEqual(values, [...values].sort((a, b) => a - b));
    const firstCard = page.locator('.call-list-card').first();
    const hiddenCardId = await firstCard.getAttribute('id');
    await assertVisibilityControlBlack(firstCard.locator('.call-list-visibility-action'));
    await screenshot(page, `call-list-${label}`);
    await Promise.all([
      page.waitForNavigation(),
      firstCard.locator('.call-list-visibility-form button').click(),
    ]);
    await page.reload();
    assert.equal(await page.locator(`#${hiddenCardId}`).count(), 0);
    await assertVisibilityControlBlack(page.getByRole('link', { name: /Показать скрытые/ }));
    await page.getByRole('link', { name: /Показать скрытые/ }).click();
    await assertVisibilityControlBlack(page.locator(`#${hiddenCardId} .call-list-visibility-action`));
    await Promise.all([
      page.waitForNavigation(),
      page.locator(`#${hiddenCardId} .call-list-visibility-form button`).click(),
    ]);
    await page.goto(`${base}/records/call-list`);
    assert.equal(await page.locator(`#${hiddenCardId}`).count(), 1);

    if (!phone) {
      await page.goto(`${base}/users`);
      const control = page.locator('.users-create-access-dropdown');
      const toggle = control.locator('.users-access-toggle');
      const assertNeutral = async () => {
        const styles = await toggle.evaluate(button => {
          const style = getComputedStyle(button);
          return [style.color, getComputedStyle(button.querySelector('i')).color,
            getComputedStyle(button.querySelector('span')).color,
            getComputedStyle(button, '::after').borderTopColor, style.backgroundColor,
            style.backgroundImage, style.boxShadow];
        });
        assert.deepEqual(styles, ['rgb(0, 0, 0)', 'rgb(0, 0, 0)', 'rgb(0, 0, 0)', 'rgb(0, 0, 0)', 'rgb(255, 255, 255)', 'none', 'none']);
      };
      await assertNeutral();
      await toggle.hover();
      await assertNeutral();
      await toggle.focus();
      await assertNeutral();
      await toggle.click();
      await control.locator('input[name=project_ids]').nth(1).check();
      await assertNeutral();
      await toggle.click();
      assert.ok((await toggle.textContent()).includes('2 объекта'));
      await assertNeutral();
      await screenshot(page, `user-project-selector-${label}`);
    }

    // Exercise recovery on desktop and installed iPhone without exhausting
    // the production login rate limit across the five viewport contexts.
    if (width === 1440 || standalone) {
      await page.goto(`${base}/appeals/new`);
      await page.selectOption('[name=apartment_id]', { index: 1 }, { force: true });
      await page.fill('[name=caller_name]', 'Проверка мобильной навигации');
      await page.fill('[name=caller_phone]', '+7 900 000-00-01');
      await page.fill('[name=body]', `Проверка обращения ${label}`);
      await Promise.all([
        page.waitForURL(/\/appeals\/\d+$/),
        page.locator('.workflow-editor button[type=submit]').click(),
      ]);
      await page.fill('[name=body]', `Комментарий ${label}`);
      await Promise.all([
        page.waitForNavigation(),
        page.locator('.workflow-page button[type=submit]').filter({ hasText: 'Отправить' }).click(),
      ]);
      assert.ok((await page.locator('.workflow-page').textContent()).includes(`Комментарий ${label}`));

      const token = await page.locator('input[name=csrf_token]').first().inputValue();
      const availability = await context.request.post(`${base}/records/availability`, { form: {
        csrf_token: token, start_date: '2026-10-21', end_date: '2026-10-21',
        start_time: standalone ? '12:00' : '10:00', end_time: standalone ? '13:00' : '11:00',
        duration: '30', weekday: '2',
      } });
      assert.equal(availability.status(), 200);
      await page.goto(`${base}/records?date=2026-10-21`);
      await page.locator('.workflow-slot a').filter({ hasText: 'Записать' }).first().click();
      await page.selectOption('[name=apartment_id]', { index: 1 }, { force: true });
      await page.fill('[name=contact]', 'Проверка записи');
      await page.fill('[name=contact_phone]', '+7 900 000-00-01');
      await Promise.all([
        page.waitForURL(url => url.pathname === '/records' && url.searchParams.get('date') === '2026-10-21'),
        page.locator('.workflow-editor button[type=submit]').filter({ hasText: 'Записать' }).click(),
      ]);
      assert.ok((await page.locator('.workflow-page').textContent()).includes('Проверка записи'));

      // Restore a valid remembered login after the short-lived session expires.
      await page.goto('about:blank');
      await context.clearCookies({ name: 'session' });
      const restored = await page.goto(`${base}/objects`);
      assert.equal(restored.status(), 200);
      assert.equal(new URL(page.url()).pathname, '/objects');

      // An expired session from a still-open form must navigate to login.
      await page.goto(`${base}/objects/1/open`);
      await page.goto(`${base}/records`);
      await context.clearCookies({ name: /^(session|remember_token)$/ });
      const [, expiredStatus] = await Promise.all([
        page.waitForURL(url => url.pathname === '/login'),
        page.evaluate(() => {
          const token = document.querySelector('input[name=csrf_token]').value;
          return fetch('/records/slots/close-interval', {
            method: 'POST', body: new URLSearchParams({ csrf_token: token }),
            headers: { Accept: 'application/json' },
          }).then(response => response.status);
        }),
      ]);
      assert.equal(expiredStatus, 401);
      await login(page);

      // Corrupt/old browser cookies recover without a manual browser reset.
      await page.goto('about:blank');
      await context.clearCookies({ name: /^(session|remember_token)$/ });
      await context.addCookies([{ name: 'remember_token', value: 'obsolete-token', url: base }]);
      await page.goto(`${base}/objects`);
      assert.equal(new URL(page.url()).pathname, '/login');
      await login(page);
    }
    assert.deepEqual(errors, []);
    console.log(`PASS auth, CSRF recovery and workflow navigation: ${label}`);
  } finally {
    await context.close();
  }
}

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.E2E_VISUAL_BROWSER_EXECUTABLE });
  try {
    for (const width of [1440, 1100, 768, 440]) await run(browser, width);
    await run(browser, 440, true);
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
