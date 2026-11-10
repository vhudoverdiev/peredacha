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
  for(const selector of ['.dashboard-redesign-hero','.workflow-mobile-shortcuts a:nth-child(1)','.workflow-mobile-shortcuts a:nth-child(2)']){
   const target=page.locator(selector);assert.deepEqual(await target.evaluate(surface),expected,selector);
   if(selector.includes('shortcuts')){await target.focus();assert.deepEqual(await target.evaluate(surface),expected);await target.hover();assert.deepEqual(await target.evaluate(surface),expected);}
  }
  for(const card of await page.locator('.dashboard-focus-card,.dashboard-info-card,.dashboard-specialist-card').all())assert.deepEqual(await card.evaluate(surface),expected,'All dashboard card backgrounds must match Tasks');
  assert.ok((await page.getByRole('link',{name:/Обращения/}).first().getAttribute('href')).startsWith('/appeals'));
  assert.ok((await page.getByRole('link',{name:/Записи/}).first().getAttribute('href')).startsWith('/records'));
 }else assert.equal(await page.locator('.workflow-mobile-shortcuts').isVisible(),false);
 const transfer=page.locator('.dashboard-handover');
 assert.equal(await transfer.evaluate(el=>getComputedStyle(el).backgroundColor),'rgba(0, 0, 0, 0)');
 assert.equal(await transfer.evaluate(el=>getComputedStyle(el).borderTopWidth),'0px');
 const news=page.locator('.dashboard-page > [data-developer-news]');
 assert.equal(await news.count(),1);
 const newsBox=await news.boundingBox();
 const hero=page.locator('.dashboard-redesign-hero');
 const heroBox=await hero.boundingBox();
 assert.ok(newsBox.y>=heroBox.y+heroBox.height-1);
 if(width>767){
  const copyBox=await hero.locator('.dashboard-redesign-copy').boundingBox();
  const transferBox=await transfer.boundingBox();
  assert.ok(Math.abs(copyBox.height-transferBox.height)<2);
  assert.match((await news.evaluate(surface)).image,/linear-gradient/);
  assert.ok(await news.evaluate(el=>parseFloat(getComputedStyle(el).borderLeftWidth)>0));
 } else {
  assert.deepEqual(await news.evaluate(surface),{image:'none',color:'rgba(0, 0, 0, 0)'});
 }
 assert.equal(await page.locator('.dashboard-subtitle').textContent(),'Вся самая необходимая информация в одном месте');
 assert.ok((await news.locator('.dev-news-eyebrow').textContent()).includes('Худовердиев В'));
 const archive=news.getByRole('link',{name:'Посмотреть все'});
 await archive.focus();
 assert.equal(await archive.evaluate(el=>getComputedStyle(el).outlineStyle),'solid');
 if(width<=767){
  const ring=transfer.locator('.dashboard-handover-ring').first();
  assert.ok(await ring.evaluate(el=>{
   const label=el.querySelector('strong');
   const previous=label.textContent;
   label.textContent='99,9%';
   const {width,height}=label.getBoundingClientRect();
   label.textContent=previous;
   const radiusInset=parseFloat(getComputedStyle(el,'::before').left);
   return Math.hypot(width,height)<=el.getBoundingClientRect().width-2*radiusInset;
  }));
 }
 for(const item of await transfer.locator('.dashboard-handover-item').all()){
  assert.equal((await item.evaluate(surface)).color,'rgb(255, 255, 255)');
 }
 if(width>767){
  const transferBox=await transfer.boundingBox();
  const heroBox=await page.locator('.dashboard-redesign-hero').boundingBox();
  const copyBox=await page.locator('.dashboard-redesign-copy').boundingBox();
  assert.ok(heroBox.x+heroBox.width-transferBox.x-transferBox.width<25);
  assert.ok(copyBox.y-transferBox.y<12);
 }
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 await page.evaluate(()=>scrollTo(0,0));await page.waitForFunction(()=>{let e=document.querySelector('.dashboard-redesign-hero');while(e){if(Number(getComputedStyle(e).opacity)<.999)return false;e=e.parentElement;}return true;});
 await page.screenshot({path:path.resolve(`_codex_chat_files/dashboard-neutral-${engine}-${width}.png`)});
 console.log(`PASS dashboard card surfaces, links and viewport: ${engine} ${width}`);
 }finally{await browser.close();}
}})().catch(e=>{console.error(e);process.exitCode=1;});
