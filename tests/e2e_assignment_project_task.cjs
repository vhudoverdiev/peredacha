const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const base=process.env.E2E_VISUAL_BASE_URL || 'http://127.0.0.1:5098';
(async()=>{
 const browser=await chromium.launch();
 try {
  for(const mobile of [false,true]) {
   const context=await browser.newContext({viewport:{width:mobile?440:1440,height:956},isMobile:mobile,hasTouch:mobile,...(mobile?{userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1'}:{})});
   const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.goto(base+'/login');await page.fill('[name=username]','e2e-admin');await page.fill('[name=password]','E2E-visual-password-2026!');await page.locator('.login-form').evaluate(e=>e.dataset.csrfReady='1');
   await Promise.all([page.waitForURL(url=>!url.pathname.includes('login')),page.locator('.login-submit').click()]);
   await page.goto(base+'/objects/1/open');await page.goto(base+'/assignments/manual/new');
   const toggle=page.locator('[name=without_premise]');const premise=page.locator('[name=apartment_id]');
   assert.equal(await premise.evaluate(e=>e.required),true);
   await toggle.check();assert.equal(await premise.isDisabled(),true);
   await toggle.uncheck();assert.equal(await premise.evaluate(e=>e.required),true);
   await toggle.check();
   const description='Общая задача без помещения '+(mobile?'телефон':'компьютер')+' '+Date.now();
   await page.locator('[name=description]').fill(description);
   await page.locator('[name=responsible_id]').selectOption({label:'Петров Пётр Петрович — Маляр'},{force:true});
   await page.locator('[name=planned_date]').fill('2026-10-21');
   if(process.env.E2E_ARTIFACT_DIR) await page.screenshot({path:`${process.env.E2E_ARTIFACT_DIR}/manual-project-task-${mobile?'phone':'desktop'}.png`,fullPage:false});
   await Promise.all([page.waitForURL(url=>url.pathname==='/assignments'),page.locator('.assignment-manual-task-form button[type=submit]').click()]);
   await page.goto(base+'/assignments?view=issued');
   const row=page.locator('.assignment-issued-row').filter({hasText:description});
   await row.waitFor();assert.ok((await row.textContent()).includes('Без помещения'));
   let navigations=0,posts=0;
   page.on('framenavigated',frame=>{if(frame===page.mainFrame())navigations++;});
   page.on('request',request=>{if(request.method()==='POST')posts++;});
   const modal=page.locator('#assignmentChangeAssigneeModal');
   for(const dismiss of ['cancel','cross','escape','backdrop']) {
    await row.locator('.js-assignment-change-assignee-open').click();await modal.waitFor({state:'visible'});
    if(dismiss==='cancel')await modal.locator('.js-assignment-change-assignee-cancel').click();
    if(dismiss==='cross')await modal.locator('.assignment-change-assignee-close').click();
    if(dismiss==='escape') {
      await page.waitForFunction(()=>document.activeElement?.closest('#assignmentChangeAssigneeModal'));
      await page.keyboard.press('Escape');
    }
    if(dismiss==='backdrop')await modal.click({position:{x:5,y:5}});
    await modal.waitFor({state:'hidden'});assert.equal(navigations,0);assert.equal(posts,0);
    console.log(mobile?'iPhone':'Desktop',dismiss,'dismissal: PASS');
   }
   if(!mobile) {
    await row.locator('.js-assignment-change-assignee-open').click();
    await modal.locator('.assignment-change-assignee-option:not(.is-current)').first().click();
    const saved=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().includes('/assignments'));
    await modal.locator('button[type=submit]').click();assert.equal((await saved).status(),200);
    await modal.waitFor({state:'hidden'});assert.equal(navigations,0);
   }
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
   assert.deepEqual(errors,[]);
   console.log(mobile?'iPhone':'Desktop','project-wide manual task and modal dismissal without navigation: PASS');
   await context.close();
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
