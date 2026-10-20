const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');
const base = process.env.E2E_VISUAL_BASE_URL || 'http://127.0.0.1:5098';
const output = process.env.E2E_ARTIFACT_DIR || path.resolve(__dirname, '../_codex_chat_files/mapping-scroll-avr');
// Run tests/e2e_visual_server.py with E2E_EXTENDED_FIXTURES=1 and a disposable DB.
async function login(page) {
  await page.goto(`${base}/login`);
  await page.fill('[name=username]', 'e2e-developer');
  await page.fill('[name=password]', 'E2E-developer-password-2026!');
  await page.locator('.login-form').evaluate(form => { form.dataset.csrfReady = '1'; });
  await Promise.all([page.waitForURL(url => !url.pathname.startsWith('/login')), page.locator('.login-submit').click()]);
  await page.goto(`${base}/objects/1/open`);
}
(async () => {
  fs.mkdirSync(output, {recursive: true});
  const browser = await chromium.launch();
  try {
    for (const width of [1440, 1100]) {
      const context = await browser.newContext({viewport: {width, height: 1000}, acceptDownloads: true});
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await login(page);
      await page.goto(`${base}/mappings`);
      const lists = page.locator('.mapping-list');
      assert.equal(await lists.count(), 3);
      for (const list of await lists.all()) {
        const numbers = await list.locator('label b').allTextContents();
        assert.deepEqual(numbers, Array.from({length:16}, (_,index)=>String(index+10))); 
      }
      const checkbox = lists.first().locator('input').nth(2);
      const selected = !(await checkbox.isChecked());
      await Promise.all([page.waitForResponse(response => response.url().includes('/mappings') && response.request().method() === 'POST'), checkbox.setChecked(selected)]);
      await page.reload();
      assert.equal(await lists.first().locator('input').nth(2).isChecked(), selected);
      await page.screenshot({path: path.join(output, `mapping-${width}.png`)});
      await page.goto(`${base}/avr?apartment_id=1`);
      await page.locator('[data-avr-open-modal]').click();
      const modal = page.locator('[data-avr-modal]');
      await modal.waitFor({state: 'visible'});
      assert.equal(await page.locator('[data-avr-developer]').inputValue(), 'Петров Пётр Петрович');
      assert.equal(await page.locator('[data-avr-developer]').isEditable(), true);
      await page.locator('[data-avr-developer]').fill('Смирнова Анна Сергеевна');
      assert.ok((await page.locator('[data-avr-phrase]').inputValue()).includes('от 01.02.2026 устранены'));
      await page.screenshot({path: path.join(output, `avr-${width}.png`)});
      const dateButton = page.locator('#avr-date').locator('..').locator('.global-date-button');
      const originalDate = await page.locator('#avr-date').inputValue();
      await dateButton.click();
      const calendar = page.locator('.js-global-date-modal:not(.d-none)');
      await calendar.waitFor();
      assert.equal(await calendar.evaluate(el => el.parentElement.id), 'avrDataModal');
      const day = calendar.locator('.assignment-date-day').filter({hasText:/^7$/});
      assert.equal(await day.evaluate(el => {const r=el.getBoundingClientRect(); return el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));}), true);
      await day.click();
      await calendar.locator('.js-global-date-save').click();
      assert.equal(await page.locator('#avr-date').inputValue(), originalDate.slice(0,7)+'-07');
      assert.equal(await modal.isVisible(), true);
      await dateButton.click();
      await page.keyboard.press('Escape');
      assert.equal(await calendar.count(), 0);
      assert.equal(await modal.isVisible(), true);
      const downloadPromise = page.waitForEvent('download');
      const postPromise = page.waitForRequest(request => new URL(request.url()).pathname === '/avr' && request.method() === 'POST');
      await page.locator('[data-avr-download]').click();
      const download = await downloadPromise;
      assert.equal(new URLSearchParams((await postPromise).postData()).get('developer_representative'), 'Смирнова Анна Сергеевна');
      assert.equal(await download.failure(), null);
      await download.saveAs(path.join(output, `avr-${width}.docx`));
      assert.deepEqual(errors, []);
      console.log(`${width}px: grouped mapping, autosave, AVR actor/date and download passed`);
      await context.close();
    }
    for (const profile of [
      {name: 'android-yandex', viewport: {width:393,height:851}, userAgent:'Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 YaBrowser/25.2.0.0 Mobile Safari/537.36'},
      {name: 'iphone-16-pro-max', viewport: {width:440,height:956}, userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1'},
    ]) {
      const {name, ...options} = profile;
      const context = await browser.newContext({...options, isMobile:true, hasTouch:true});
      const page = await context.newPage();
      await login(page);
      const cdp = await context.newCDPSession(page);
      for (const route of ['/objects','/tasks','/apartments','/account']) {
        await page.goto(base+route);
        await page.waitForLoadState('networkidle');
        assert.equal(new URL(page.url()).pathname, route);
        const dimensions = await page.evaluate(() => ({height: document.scrollingElement.scrollHeight, viewport: innerHeight}));
        if (name === 'android-yandex' && dimensions.height > dimensions.viewport + 5) {
          await cdp.send('Input.synthesizeScrollGesture', {x:200,y:550,yDistance:-450,speed:600,gestureSourceType:'touch'});
          assert.ok(await page.evaluate(() => scrollY > 20), `${name} ${route}: swipe must scroll`);
        }
        if (name === 'android-yandex') {
          assert.equal(await page.evaluate(() => getComputedStyle(document.body).overscrollBehaviorY), 'auto');
          assert.equal(await page.evaluate(() => getComputedStyle(document.documentElement).overscrollBehaviorY), 'none');
        } else {
          assert.equal(await page.evaluate(() => document.documentElement.classList.contains('android-touch-device')), false);
        }
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
        await page.screenshot({path:path.join(output, `${name}-${route.slice(1)}.png`)});
      }
      if (name === 'android-yandex') {
        await page.goto(`${base}/tasks/1`);
        await page.locator('.task-detail-delete-btn').click();
        await page.locator('.js-crm-confirm-modal:not(.d-none)').waitFor();
        const beforeModalSwipe = await page.evaluate(() => scrollY);
        await cdp.send('Input.synthesizeScrollGesture', {x:200,y:550,yDistance:-350,speed:600,gestureSourceType:'touch'});
        assert.equal(await page.evaluate(() => scrollY), beforeModalSwipe, 'confirmation must keep background stationary');
        await page.locator('.js-crm-confirm-cancel').click();
        assert.equal(await page.locator('.task-detail-delete-btn').isEnabled(), true);
      }
      console.log(name === 'android-yandex' ? `${name}: objects, remarks, premises and account touch scrolling passed` : `${name}: layout and isolation from Android scroll rules passed`);
      await context.close();
    }
  } finally { await browser.close(); }
})().catch(error => {console.error(error);process.exitCode=1;});
