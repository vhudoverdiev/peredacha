const assert=require('node:assert/strict');const {chromium}=require('playwright');
if (!process.env.E2E_ARTIFACT_DIR) throw new Error('Set E2E_ARTIFACT_DIR to a scratch directory');
const base=process.env.E2E_VISUAL_BASE_URL || 'http://127.0.0.1:5098';
(async()=>{
 const browser=await chromium.launch();
 try{
 for(const [role,width,kind] of [['painter',1440,'desktop'],['handyman',1100,'desktop'],['glazier',440,'iphone'],['painter',412,'android']]){
  const mobile=kind!=='desktop';const android=kind==='android';
  const context=await browser.newContext({viewport:{width,height:mobile?956:1000},isMobile:mobile,hasTouch:mobile,...(mobile?{userAgent:android?'Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36':'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1'}:{})});
  const page=await context.newPage();let navigations=0;page.on('framenavigated',frame=>{if(frame===page.mainFrame())navigations++;});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/login');await page.fill('[name=username]','qa-'+role);await page.fill('[name=password]','Worker-qa-password-2026!');await page.locator('.login-form').evaluate(f=>f.dataset.csrfReady='1');
  await Promise.all([page.waitForURL('**/my-tasks'),page.locator('.login-submit').click()]);
  assert.equal(await page.locator('#appSidebar').count(),0);
  if(!mobile){const bounds=await page.locator('.app-topbar').boundingBox();assert.ok(bounds.x<2,'No sidebar space may remain: '+bounds.x);}assert.equal(await page.locator('html').evaluate(e=>e.classList.contains('desktop-shell-with-sidebar')),false);
  assert.equal(await page.locator('[data-worker-project-group]').count(),2);
  assert.equal(await page.getByText('Объект: не назначен',{exact:true}).count(),0);
  const header=page.locator('.worker-project-heading').first();
  assert.equal(await header.locator('i.bi-buildings').count(),1);
  assert.equal(await header.evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(255, 255, 255)');
  assert.equal(await header.evaluate(e=>getComputedStyle(e).backgroundImage),'none');
  if(!mobile) assert.equal(await page.locator('.worker-brand-link .brand-text').evaluate(e=>getComputedStyle(e).color),'rgb(255, 255, 255)');
  const navigationBeforeActions=navigations;
  const card=page.locator('[data-worker-task-card]').first();const id=await card.getAttribute('data-task-id');
  const status=card.locator('[name=status][value=in_progress]');await status.click();await page.waitForFunction(id=>document.querySelector(`[data-task-id="${id}"] [data-worker-status-pill]`).textContent==='В работе',id);
  assert.equal(await page.locator(`[data-task-id="${id}"]`).count(),1);assert.ok(page.url().includes('/my-tasks'));
  await card.locator('[data-worker-comment-toggle]').click();const draft='Комментарий '+kind+' '+Date.now()+' <b>проверка</b>';await card.locator('textarea').fill(draft);
  await card.locator('[data-worker-comment-close]').click();
  assert.equal(await card.locator('.worker-task-discussion').isVisible(),false);
  await card.locator('[data-worker-comment-toggle]').click();
  assert.equal(await card.locator('textarea').inputValue(),draft);
  assert.equal(await card.locator('[data-worker-comment-toggle]').evaluate(e=>getComputedStyle(e).color),'rgb(0, 0, 0)');
  assert.equal(await card.locator('[data-worker-comment-close]').evaluate(e=>getComputedStyle(e).color),'rgb(0, 0, 0)');
  await card.locator('textarea').scrollIntoViewIfNeeded();
  await page.screenshot({path:`${process.env.E2E_ARTIFACT_DIR}/worker-comment-open-${kind}-${width}.png`,fullPage:false});
  const commentUrl=`**/my-tasks/${id}/comment`;
  await page.route(commentUrl,route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({ok:false,message:'Временная ошибка'})}));
  await card.locator('[data-worker-comment-form] button[type=submit]').click();
  await card.locator('[data-worker-comment-error]:not([hidden])').waitFor();
  assert.equal(await card.locator('textarea').inputValue(),draft);
  assert.equal(await card.locator('[data-worker-comment-toggle]').evaluate(e=>getComputedStyle(e).color),'rgb(0, 0, 0)');
  assert.equal(await card.locator('[data-worker-comment-close]').evaluate(e=>getComputedStyle(e).color),'rgb(0, 0, 0)');
  await page.unroute(commentUrl);
  await card.locator('[data-worker-comment-form] button[type=submit]').click();await card.locator('[data-worker-comment-feedback]:not([hidden])').waitFor();
  assert.equal(await card.locator('[data-worker-comments]').count(),0);
  assert.equal(await card.locator('.worker-task-discussion').isVisible(),false);
  assert.equal(await card.locator('textarea').inputValue(),'');
  await card.locator('[data-worker-own-comments]').getByText(draft,{exact:true}).waitFor();
  assert.equal(await card.locator('[data-worker-own-comments] b').count(),0);
  assert.equal(await card.locator('[data-worker-comment-feedback]').innerText(),'Комментарий отправлен');
  assert.equal(await card.locator('[data-worker-status-form] button[name=status]').count(),2);
  await page.waitForFunction(id=>{
    const style=getComputedStyle(document.querySelector(`[data-task-id="${id}"] .worker-progress-action`));
    return style.color==='rgb(31, 37, 43)' && style.backgroundColor==='rgb(227, 230, 233)';
  },id);
  await card.locator('[name=status][value=done]').click();await page.waitForFunction(id=>document.querySelector(`[data-task-id="${id}"]`).classList.contains('done'),id);
  assert.equal(await card.locator('[data-worker-done-toggle]').innerText(),'Не выполнено');
  await page.waitForFunction(id=>getComputedStyle(document.querySelector(`[data-task-id="${id}"] .worker-task-text`)).color==='rgb(0, 0, 0)',id);
  assert.equal(await card.locator('.worker-task-text').evaluate(e=>getComputedStyle(e).textDecorationColor),'rgb(0, 0, 0)');
  await page.screenshot({path:`${process.env.E2E_ARTIFACT_DIR}/worker-done-${kind}-${width}.png`,fullPage:false});
  assert.ok(await card.locator('[data-worker-done-toggle]').evaluate(e=>getComputedStyle(e).backgroundImage.includes('gradient')));
  await page.waitForFunction(id=>document.querySelector(`[data-task-id="${id}"] [data-worker-done-toggle]`).classList.contains('is-active'),id);
  await card.locator('[data-worker-done-toggle]').click();
  await page.waitForFunction(id=>!document.querySelector(`[data-task-id="${id}"]`).classList.contains('done'),id);
  await page.locator(`[data-task-id="${id}"] [name=status][value=in_progress]`).click();await page.waitForFunction(id=>!document.querySelector(`[data-task-id="${id}"]`).classList.contains('done'),id);
  assert.equal(await page.locator('[data-worker-done-count]').innerText(),'0');
  assert.equal(navigations,navigationBeforeActions,'Actions should not reload the page');
  if(mobile){
   await page.evaluate(()=>window.scrollTo(0,document.body.scrollHeight));
   const dock=page.locator('nav.mobile-bottom-nav-root');const box=await dock.boundingBox();assert.ok(Math.abs(box.y+box.height-956)<2,JSON.stringify(box));
   if(android){
    assert.equal(await page.locator('html').evaluate(e=>getComputedStyle(e).colorScheme),'dark');
    const cdp=await context.newCDPSession(page);
    try{await cdp.send('Emulation.setSafeAreaInsets',{insets:{bottom:24,left:0,right:0,top:0}});const insetBox=await dock.boundingBox();assert.equal(Math.round(insetBox.height),96);console.log('Android safe area 24px: dark dock extends to edge');}
    catch(e){if(!e.message.includes('wasn\'t found')&&!e.message.includes('not found'))throw e;await page.evaluate(()=>document.documentElement.style.setProperty('--android-dock-inset','24px')); const area=await dock.boundingBox(); assert.equal(Math.round(area.height),96); assert.equal(await dock.evaluate(e=>getComputedStyle(e).paddingBottom),'27px'); console.log('Android simulated safe area 24px: OK');}
   }
  }
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  await page.screenshot({path:`${process.env.E2E_ARTIFACT_DIR}/worker-${kind}-${width}.png`,fullPage:!mobile});
  const commentEntry=card.locator('.worker-task-comment-entry').filter({hasText:draft});
  await commentEntry.locator('.worker-comment-delete-button').click();
  await page.locator('.js-crm-confirm-cancel').click();
  assert.equal(await commentEntry.count(),1);
  await commentEntry.locator('.worker-comment-delete-button').click();
  await page.locator('.js-crm-confirm-ok').click();
  await commentEntry.waitFor({state:'detached'});
  assert.equal(navigations,navigationBeforeActions,'Deleting a comment must not reload');
  assert.deepEqual(errors,[]);console.log(role,kind,width,'status/comment/layout OK');await context.close();
 }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
