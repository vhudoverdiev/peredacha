const assert=require('node:assert/strict'),path=require('node:path');
const {chromium,firefox,webkit}=require('playwright');const base='http://127.0.0.1:5098';
(async()=>{for(const engine of ['chromium','firefox','webkit']){
 const browser=await({chromium,firefox,webkit}[engine].launch(engine==='chromium'?{executablePath:process.env.E2E_VISUAL_BROWSER_EXECUTABLE}:{}));
 try{const page=await browser.newPage({viewport:{width:engine==='webkit'?440:1440,height:956},serviceWorkers:'block',isMobile:engine==='webkit',hasTouch:engine==='webkit',...(engine==='webkit'?{userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1'}:{})});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/login');await page.fill('[name=username]','e2e-developer');await page.fill('[name=password]','E2E-developer-password-2026!');await page.locator('.login-submit').click();await page.waitForURL(u=>!u.pathname.startsWith('/login'));await page.goto(base+'/objects/1/open');await page.goto(base+'/');
 await page.evaluate(()=>{window.__navigationSentinel=42;window.__oldChrome=document.querySelector('.app-topbar,.mobile-project-topbar');});
 let navigations=0;page.on('request',request=>{if(request.isNavigationRequest()&&request.frame()===page.mainFrame())navigations++;});
 async function open(href){await page.evaluate(href=>{const a=document.createElement('a');a.href=href;a.textContent='Navigation test';document.body.append(a);a.click();a.remove();},href);await page.waitForURL(u=>u.pathname+u.search===href);await page.waitForFunction(()=>window.crmPageLoading===false);assert.equal(await page.evaluate(()=>window.__navigationSentinel),42);assert.equal(await page.evaluate(()=>window.__oldChrome===document.querySelector('.app-topbar,.mobile-project-topbar')),true);}
 if(engine!=='webkit'){await page.locator('.app-sidebar a[href="/tasks"]').click();await page.waitForURL('**/tasks');await page.waitForFunction(()=>window.crmPageLoading===false);}
 for(const href of ['/tasks','/apartments','/records','/appeals','/appeals/new'])await open(href);
 await page.locator('[name=body]').fill('Сохранённый текст обращения');
 await open('/tasks');await page.goBack();await page.waitForURL('**/appeals/new');await page.waitForFunction(()=>window.crmPageLoading===false);await page.waitForFunction(()=>document.querySelector('[name=body]')?.value==='Сохранённый текст обращения');
 await open('/tasks/new?mode=manual&kind=act');await page.locator('[data-act-add]').click();assert.equal(await page.locator('[data-act-row]').count(),2);
 await open('/records');await page.locator('.workflow-view-switch a').filter({hasText:'Неделя'}).click();await page.waitForURL('**/records?*view=week*');await page.waitForFunction(()=>document.querySelector('.records-page')?.dataset.recordsView==='week');
 assert.equal(navigations,0);assert.deepEqual(errors,[]);console.log(`PASS persistent shell, section links, back draft, page initialization: ${engine}`);
 }finally{await browser.close();}
}})().catch(e=>{console.error(e);process.exitCode=1;});
