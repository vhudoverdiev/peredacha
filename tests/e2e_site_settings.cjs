const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const base = process.env.E2E_VISUAL_BASE_URL || 'http://127.0.0.1:5098';
const artifacts = process.env.E2E_ARTIFACT_DIR;
if (!artifacts) throw new Error('Set E2E_ARTIFACT_DIR');
async function login(page, developer) {
  await page.goto(base + '/login');
  await page.fill('[name=username]', developer ? 'e2e-developer' : 'e2e-admin');
  await page.fill('[name=password]', developer ? 'E2E-developer-password-2026!' : 'E2E-visual-password-2026!');
  await page.locator('.login-form').evaluate(f => f.dataset.csrfReady = '1');
  await Promise.all([page.waitForURL(url => !url.pathname.includes('login')), page.locator('.login-submit').click()]);
}
async function toggle(page, selector, enabled) {
  const response = page.waitForResponse(r => r.url().endsWith('/settings') && r.request().method() === 'POST');
  await page.locator(selector).setChecked(enabled);
  assert.equal((await response).status(), 200);
}
(async () => {
 const browser = await chromium.launch();
 try {
  const adminContext = await browser.newContext({viewport:{width:1440,height:1000}});
  const page = await adminContext.newPage();
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  await login(page, true);
  await page.goto(base + '/settings');
  assert.equal(await page.locator('[name=blocked_site_sections]').count(),12);
  assert.equal(await page.locator('a[href="/documents"]').count(),0);
  const managerContext = await browser.newContext();
  const manager = await managerContext.newPage(); await login(manager, false);
  await manager.goto(base+'/objects');
  await manager.goto(base+'/objects/1/open');
  await toggle(page, '#section-lock-dashboard', true);
  assert.equal((await manager.goto(base+'/')).status(),503);
  assert.equal((await manager.request.get(base+'/objects')).status(),200);
  assert.equal((await page.request.get(base+'/')).status(),200);
  await toggle(page, '#section-lock-dashboard', false);
  assert.equal((await manager.goto(base+'/')).status(),200);
  await toggle(page, '#section-lock-apartments', true);
  assert.equal((await manager.request.get(base+'/apartments')).status(),503);
  assert.equal((await manager.request.get(base+'/avr')).status(),200);
  await toggle(page, '#section-lock-apartments', false);
  await toggle(page, '#section-lock-avr', true);
  assert.equal((await manager.request.get(base+'/avr')).status(),503);
  assert.equal((await manager.request.get(base+'/apartments')).status(),200);
  await toggle(page, '#section-lock-avr', false);
  assert.equal(await page.locator('#section-lock-administration').count(),0);
  await toggle(page, '#section-lock-assignments', true);
  assert.equal((await manager.request.get(base+'/assignments')).status(),503);
  assert.equal((await manager.request.get(base+'/report')).status(),200);
  await toggle(page, '#section-lock-assignments', false);
  await toggle(page, '#section-lock-report', true);
  assert.equal((await manager.request.get(base+'/report')).status(),503);
  assert.equal((await manager.request.get(base+'/assignments')).status(),200);
  await toggle(page, '#section-lock-report', false);
  await toggle(page, '#site-maintenance-setting', true);
  assert.equal((await manager.goto(base+'/objects')).status(),503);
  assert.equal((await page.request.get(base+'/objects')).status(),200);
  await toggle(page, '#site-maintenance-setting', false);
  const phoneContext = await browser.newContext({viewport:{width:440,height:956},isMobile:true,hasTouch:true,userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1'});
  const phone = await phoneContext.newPage(); await login(phone,false);
  await toggle(page, '#mobile-dev-setting', true);
  assert.equal((await phone.goto(base+'/objects')).status(),503);
  assert.equal((await phone.request.get(base+'/account')).status(),503);
  assert.equal((await manager.goto(base+'/objects')).status(),200);
  await toggle(page, '#mobile-dev-setting', false);
  assert.equal((await phone.goto(base+'/objects')).status(),200);
  await manager.goto(base+'/apartments/1');
  const phones = '+7 921 490-58-00\n+7 902 507-' + String(Date.now()).slice(-4);
  const saved = manager.waitForResponse(r=>r.url().endsWith('/apartments/1/details') && r.request().method()==='POST');
  await manager.locator('[name=phone]').fill(phones);
  await manager.locator('[name=phone]').blur();
  assert.equal((await saved).status(),200);
  await manager.reload();
  assert.equal(await manager.locator('textarea[name=phone]').inputValue(),phones);
  for (const width of [1440,1100]) {
    await manager.setViewportSize({width,height:956});
    await manager.reload();
    const field=manager.locator('textarea[name=phone]');
    assert.equal(await field.inputValue(),phones);
    assert.equal(await field.evaluate(e=>e.scrollHeight<=e.clientHeight+2),true);
    assert.equal(await manager.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
    await manager.waitForTimeout(700);
    await manager.screenshot({path:`${artifacts}/apartment-phones-${width}.png`,fullPage:false});
  }
  for (const width of [1440,1100]) {
    await page.setViewportSize({width,height:width===440?956:1000});
    await page.reload();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
    await page.waitForTimeout(700);
    await page.screenshot({path:`${artifacts}/settings-${width}.png`,fullPage:true});
  }
  await phone.goto(base+'/apartments/1');
  assert.equal(await phone.locator('textarea[name=phone]').inputValue(),phones);
  assert.equal(await phone.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  await phone.waitForTimeout(700);
  await phone.screenshot({path:`${artifacts}/apartment-phones-iphone.png`,fullPage:true});
  const developerPhoneContext = await browser.newContext({viewport:{width:440,height:956},isMobile:true,hasTouch:true,userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1'});
  const developerPhone=await developerPhoneContext.newPage(); await login(developerPhone,true);
  await developerPhone.goto(base+'/settings');
  await developerPhone.waitForTimeout(700);
  assert.equal(await developerPhone.locator('.settings-grid').evaluate(e=>getComputedStyle(e).gridTemplateColumns.split(' ').length),1);
  assert.equal(await developerPhone.locator('.settings-section-lock-grid').evaluate(e=>getComputedStyle(e).gridTemplateColumns.split(' ').length),1);
  assert.equal(await developerPhone.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  await developerPhone.screenshot({path:`${artifacts}/settings-iphone.png`,fullPage:true});
  for (const path of ['/documents','/documents/addendum','/documents/download/test.docx']) assert.equal((await page.request.get(base+path)).status(),404);
  assert.deepEqual(errors,[]);
  console.log('Settings: autosave, locks, developer exemption, mobile closure, reopening and 3 viewport sizes PASS');
 } finally { await browser.close(); }
})().catch(e=>{ console.error(e); process.exitCode=1; });
