const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{const browser=await chromium.launch();try{for(const width of [1440,1100,440]){
 const context=await browser.newContext({viewport:{width,height:956},isMobile:width===440,hasTouch:width===440,...(width===440?{userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1'}:{})});
 const page=await context.newPage();const base=process.env.E2E_VISUAL_BASE_URL||'http://127.0.0.1:5098';
 await page.goto(base+'/login');await page.fill('[name=username]','e2e-admin');await page.fill('[name=password]','E2E-visual-password-2026!');await page.locator('.login-form').evaluate(e=>e.dataset.csrfReady='1');
 await Promise.all([page.waitForURL(u=>!u.pathname.includes('login')),page.locator('.login-submit').click()]);await page.goto(base+'/objects/1/open');await page.goto(base+'/apartments/1');
 const button=page.locator('.apartment-source-export-btn');assert.ok(await button.isVisible());
 const [download]=await Promise.all([page.waitForEvent('download'),button.click()]);assert.ok(download.suggestedFilename().endsWith('.xlsx'));assert.equal(await download.failure(),null);
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));console.log('PASS apartment Excel '+width);await context.close();
}}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
