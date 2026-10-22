const assert=require('node:assert/strict');
const {chromium,webkit}=require('playwright');
const base=process.env.E2E_VISUAL_BASE_URL||'http://127.0.0.1:5098';
(async()=>{
  for(const [engine,width] of [['chromium',1440],['chromium',1024],['webkit',440]]) {
    const browser=await(engine==='webkit'?webkit.launch():chromium.launch({executablePath:process.env.E2E_VISUAL_BROWSER_EXECUTABLE}));
    try {
      const context=await browser.newContext({viewport:{width,height:956},serviceWorkers:'block',isMobile:engine==='webkit',hasTouch:engine==='webkit',
        ...(engine==='webkit'?{userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1'}:{})});
      const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
      await page.goto(base+'/login');await page.fill('[name=username]','e2e-developer');await page.fill('[name=password]','E2E-developer-password-2026!');
      await page.locator('.login-submit').click();await page.waitForURL(url=>!url.pathname.startsWith('/login'));
      await page.goto(base+'/objects/1/open');await page.goto(base+'/records/availability');
      const field=page.locator('[data-time-field]').first(),input=field.locator('input');
      await input.fill('16');
      await page.locator('.crm-time-options button').first().waitFor();
      assert.ok((await page.locator('.crm-time-options button').allTextContents()).every(text=>text.startsWith('16:')));
      await page.locator('.crm-time-options button').filter({hasText:/^16:15$/}).click();
      assert.equal(await input.inputValue(),'16:15');
      await input.fill('0910');await input.blur();assert.equal(await input.inputValue(),'09:10');
      await field.locator('button').click();
      await page.locator('.crm-time-options button').filter({hasText:/^09:15$/}).click();
      assert.equal(await input.inputValue(),'09:15');
      await input.fill('25:00');assert.equal(await input.evaluate(el=>el.checkValidity()),false);
      await input.fill('09:10');await input.press('ArrowDown');
      await page.locator('.crm-time-options button:focus').press('Enter');
      assert.equal(await page.locator('.crm-time-options').count(),0);
      await page.goto(base+'/records');await page.locator('[data-close-interval-open]').click();
      const modal=page.locator('[data-close-interval-modal]');
      await modal.locator('[name=start_time]').fill('09:10');
      await modal.locator('[name=end_time]').fill('10:20');
      await modal.locator('[data-time-field] button').first().click();
      const box=await page.locator('.crm-time-options').boundingBox();
      assert.ok(box.x>=0&&box.x+box.width<=width+1&&box.y>=0&&box.y+box.height<=956+1);
      await page.locator('.crm-time-options button').filter({hasText:/^09:30$/}).click();
      assert.equal(await modal.locator('[name=start_time]').inputValue(),'09:30');
      await modal.locator('[data-close-interval-dismiss]').first().click();
      assert.deepEqual(errors,[]);
      console.log(`PASS keyboard, list, validation and modal placement: ${engine} ${width}`);
      await context.close();
    } finally {await browser.close();}
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
