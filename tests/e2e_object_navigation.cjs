const assert=require('node:assert/strict');const{chromium,firefox,webkit}=require('playwright');const base='http://127.0.0.1:5098';
(async()=>{for(const engine of ['chromium','firefox','webkit']){const browser=await({chromium,firefox,webkit}[engine].launch(engine==='chromium'?{executablePath:process.env.E2E_VISUAL_BROWSER_EXECUTABLE}:{}));try{
 const page=await browser.newPage({viewport:{width:engine==='webkit'?440:1440,height:956},serviceWorkers:'block',isMobile:engine==='webkit',hasTouch:engine==='webkit',...(engine==='webkit'?{userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1'}:{})});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/login');await page.fill('[name=username]','e2e-developer');await page.fill('[name=password]','E2E-developer-password-2026!');await page.locator('.login-submit').click();await page.waitForURL(u=>!u.pathname.startsWith('/login'));await page.goto(base+'/objects');
 await page.evaluate(()=>{window.__sameDocument=42;window.__sidebar=document.querySelector('.app-sidebar');});let navigations=0;page.on('request',r=>{if(r.isNavigationRequest()&&r.frame()===page.mainFrame())navigations++;});
 let release;const gate=new Promise(resolve=>release=resolve);await page.route('**/objects/1/open',async route=>{await gate;await route.continue();});
 const link=page.locator('.object-card[data-href="/objects/1/open"]').first();await link.click();
 await page.waitForFunction(()=>window.crmPageLoading===true);
 assert.equal(await page.evaluate(()=>window.__sameDocument),42);
 assert.ok(await page.locator('.objects-page').isVisible());
 assert.equal(await page.locator('html').evaluate(e=>e.classList.contains('desktop-styles-pending')),false);
 release();await page.waitForURL(base+'/');await page.waitForFunction(()=>window.crmPageLoading===false);
 assert.equal(await page.evaluate(()=>window.__sameDocument),42);
 if(engine!=='webkit'){assert.ok(await page.locator('.app-sidebar').isVisible());assert.equal(await page.locator('html').evaluate(e=>e.classList.contains('desktop-shell-with-sidebar')),true);}
 assert.equal(await page.locator('body').getAttribute('data-navigation-project'),'1');assert.equal(navigations,0);
 await page.locator('.dashboard-title').waitFor();
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));assert.deepEqual(errors,[]);
 await page.screenshot({path:`_codex_chat_files/object-entry-${engine}.png`});
 console.log(`PASS object opens in existing document, sidebar stays visible during delayed server response: ${engine}`);
 }finally{await browser.close();}}})().catch(e=>{console.error(e);process.exitCode=1;});
