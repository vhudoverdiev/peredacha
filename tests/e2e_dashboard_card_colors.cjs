const assert=require('node:assert/strict'),path=require('node:path');
const {chromium,webkit}=require('playwright');
const base='http://127.0.0.1:5098';
(async()=>{for(const[engine,width]of[['chromium',1440],['chromium',1024],['webkit',440]]){
 const browser=await(engine==='webkit'?webkit.launch():chromium.launch({executablePath:process.env.E2E_VISUAL_BROWSER_EXECUTABLE}));
 try{const page=await browser.newPage({viewport:{width,height:956},serviceWorkers:'block',isMobile:engine==='webkit',hasTouch:engine==='webkit',...(engine==='webkit'?{userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1'}:{})});
 await page.goto(base+'/login');await page.fill('[name=username]','e2e-admin');await page.fill('[name=password]','E2E-visual-password-2026!');await page.locator('.login-submit').click();await page.waitForURL(u=>!u.pathname.startsWith('/login'));await page.goto(base+'/');
 const surface=el=>({image:getComputedStyle(el).backgroundImage,color:getComputedStyle(el).backgroundColor});
 if(width===440){
  const expected=await page.locator('.dashboard-focus-primary').evaluate(surface);
  for(const selector of ['.dashboard-redesign-hero','.dashboard-progress-panel','.workflow-mobile-shortcuts a:nth-child(1)','.workflow-mobile-shortcuts a:nth-child(2)']){
   const target=page.locator(selector);assert.deepEqual(await target.evaluate(surface),expected,selector);
   if(selector.includes('shortcuts')){await target.focus();assert.deepEqual(await target.evaluate(surface),expected);await target.hover();assert.deepEqual(await target.evaluate(surface),expected);}
  }
  assert.ok((await page.getByRole('link',{name:/Обращения/}).first().getAttribute('href')).startsWith('/appeals'));
  assert.ok((await page.getByRole('link',{name:/Записи/}).first().getAttribute('href')).startsWith('/records'));
 }else assert.equal(await page.locator('.workflow-mobile-shortcuts').isVisible(),false);
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 await page.evaluate(()=>scrollTo(0,0));await page.waitForFunction(()=>{let e=document.querySelector('.dashboard-redesign-hero');while(e){if(Number(getComputedStyle(e).opacity)<.999)return false;e=e.parentElement;}return true;});
 await page.screenshot({path:path.resolve(`_codex_chat_files/dashboard-neutral-${engine}-${width}.png`)});
 console.log(`PASS dashboard card surfaces, links and viewport: ${engine} ${width}`);
 }finally{await browser.close();}
}})().catch(e=>{console.error(e);process.exitCode=1;});
