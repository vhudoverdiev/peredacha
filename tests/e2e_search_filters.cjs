const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const base = process.env.E2E_VISUAL_BASE_URL || 'http://127.0.0.1:5098';
(async()=>{
 const browser=await chromium.launch();
 try {
  for (const mobile of [false,true]) {
   const context=await browser.newContext({viewport:{width:mobile?440:1440,height:956},isMobile:mobile,hasTouch:mobile,...(mobile?{userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1'}:{})});
   const page=await context.newPage(); const errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.goto(base+'/login');await page.fill('[name=username]','e2e-admin');await page.fill('[name=password]','E2E-visual-password-2026!');await page.locator('.login-form').evaluate(e=>e.dataset.csrfReady='1');
   await Promise.all([page.waitForURL(url=>!url.pathname.includes('login')),page.locator('.login-submit').click()]);
   await page.goto(base+'/objects/1/open');
   const routes=['/tasks','/contractors','/apartments','/glass-measurements','/assignments',...(!mobile?['/materials?tab=writeoff']:[])];
   for (const path of routes) {
    await page.goto(base+path);
    const input=page.locator('form[method=get] input[name=q]:not([type=hidden])').first();
    if(mobile && path==='/contractors') { assert.equal(await input.count(),0); continue; }
    assert.equal(await input.count(),1,'Search field '+path);
    await input.fill('1');await input.press('Enter');
    await page.waitForURL(url=>url.searchParams.get('q')==='1');
    assert.equal(new URL(page.url()).searchParams.get('q'),'1');
   }
   await page.goto(base+'/apartments');
   await page.locator('select[name=inspection_status]').selectOption('was',{force:true});
   await page.waitForURL(url=>url.searchParams.get('inspection_status')==='was');
   await page.locator('input[name=finishing_group][value=white]').check();
   await page.waitForURL(url=>url.searchParams.getAll('finishing_group').includes('white'));
   await page.goto(base+'/tasks');
   await page.locator('select[name=status]').selectOption('done',{force:true});
   await page.waitForURL(url=>url.searchParams.get('status')==='done');
   const brand=mobile?page.locator('.mobile-project-topbar .mobile-shell-brand'):page.locator('#appSidebar .sidebar-brand-link');
   assert.equal(await brand.getAttribute('href'),'/objects');
   await brand.click();await page.waitForURL('**/objects');
   assert.ok(await page.locator('.object-card').count()>0);
   assert.deepEqual(errors,[]);
   console.log(mobile?'iPhone':'Desktop','Enter in all search tabs, immediate select/checkbox filters, brand -> objects: PASS');
   await context.close();
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
