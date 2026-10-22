const assert=require('node:assert/strict');
const path=require('node:path');
const {chromium,webkit}=require('playwright');
// Use only the disposable fixtures from tests/e2e_visual_server.py.
(async()=>{
 for(const [engine,width] of [['chromium',1440],['chromium',1024],['webkit',440]]){
  const browser=await(engine==='webkit'?webkit.launch():chromium.launch({executablePath:process.env.E2E_VISUAL_BROWSER_EXECUTABLE}));
  try{
   const page=await browser.newPage({viewport:{width,height:956},serviceWorkers:'block',isMobile:engine==='webkit',hasTouch:engine==='webkit',...(engine==='webkit'?{userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1'}:{})});
   await page.goto('http://127.0.0.1:5098/login');await page.fill('[name=username]','e2e-developer');await page.fill('[name=password]','E2E-developer-password-2026!');await page.locator('.login-submit').click();await page.waitForURL(u=>!u.pathname.startsWith('/login'));
   for(const [name,url] of [['updates','/developer/updates'],['messages','/developer/updates?mode=messages'],['archive','/updates']]){
    await page.goto('http://127.0.0.1:5098'+url);
    const card=page.locator('.dev-news-empty');await card.waitFor();
    assert.equal(await card.locator('.dev-news-empty-icon i').count(),1);
    assert.equal(await card.evaluate(e=>getComputedStyle(e).textAlign),'left');
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    await page.waitForFunction(()=>{let e=document.querySelector('.dev-news-empty');while(e){if(Number(getComputedStyle(e).opacity)<.999)return false;e=e.parentElement;}return true;});
    await page.screenshot({path:path.resolve(`_codex_chat_files/news-empty-${name}-${engine}-${width}.png`)});
   }
   console.log(`PASS empty update/message/archive cards ${engine} ${width}`);
  }finally{await browser.close();}
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
