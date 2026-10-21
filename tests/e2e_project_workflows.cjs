const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const fs=require('node:fs');
const base=process.env.E2E_VISUAL_BASE_URL||'http://127.0.0.1:5098';
(async()=>{const browser=await chromium.launch();try{
for(const width of [1440,1100,440]){
 const context=await browser.newContext({viewport:{width,height:956},isMobile:width===440,hasTouch:width===440,...(width===440?{userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1'}:{})});
 const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/login');await page.fill('[name=username]','e2e-office-manager');await page.fill('[name=password]','E2E-office-password-2026!');await page.locator('.login-form').evaluate(e=>e.dataset.csrfReady='1');
 await Promise.all([page.waitForURL(u=>!u.pathname.includes('login')),page.locator('.login-submit').click()]);
 await page.goto(base+'/objects/1/open');await page.goto(base+'/appeals/new');
 await page.selectOption('[name=apartment_id]',{index:1},{force:true});
 await page.fill('[name=caller_name]','Петров Пётр Петрович');
 await page.fill('[name=caller_phone]','+7 921 000-00-02');
 await page.fill('[name=body]','Проверка обращения '+width);
 await page.setInputFiles('[name=attachment]',width===1440?{name:'акт.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4\n%%EOF\n')}:{name:'фото.jpeg',mimeType:'image/jpeg',buffer:Buffer.from([0xff,0xd8,0xff,0xe0,0x4a,0x50,0x45,0x47])});
 await Promise.all([page.waitForURL(/appeals\/\d+$/),page.locator('.workflow-editor button[type=submit]').click()]);
 await page.fill('[name=body]','Комментарий инженера');
 await Promise.all([page.waitForNavigation(),page.locator('.workflow-page button[type=submit]').filter({hasText:'Отправить'}).click()]);
 assert.ok((await page.locator('.workflow-page').textContent()).includes('Комментарий инженера'));
 assert.ok((await page.locator('.appeal-premise-card').textContent()).includes('Owner 1'));
 assert.ok((await page.locator('.appeal-premise-card').textContent()).includes('+7 900 000-0001'));
 assert.ok((await page.locator('.appeal-caller-card').textContent()).includes('Петров Пётр Петрович'));
 assert.ok((await page.locator('.appeal-caller-card').textContent()).includes('+7 921 000-00-02'));
 const attachment=page.locator('.appeal-attachment-card');assert.equal(await attachment.count(),1);
 assert.ok((await attachment.textContent()).includes(width===1440?'акт.pdf':'фото.jpeg'));
 const attachmentResponse=await context.request.get(await attachment.getAttribute('href'));assert.equal(attachmentResponse.status(),200);
 assert.equal(await page.locator('.workflow-nav').count(),0);
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`appeal overflow ${width}`);
 await page.waitForTimeout(900);
 if(process.env.E2E_ARTIFACT_DIR)await page.screenshot({path:`${process.env.E2E_ARTIFACT_DIR}/appeal-detail-${width}.png`,fullPage:false});
 await Promise.all([page.waitForNavigation(),page.locator('button[name=status][value=in_progress]').click()]);
 await Promise.all([page.waitForURL(/\/appeals$/),page.locator('a').filter({hasText:'К обращениям'}).click()]);
 const listCard=page.locator('.workflow-appeal-card').first();
 assert.ok((await listCard.textContent()).includes('Owner 1'));
 assert.ok((await listCard.textContent()).includes('+7 900 000-0001'));
 assert.equal(await page.locator('.workflow-nav').count(),0);
 if(process.env.E2E_ARTIFACT_DIR)await page.screenshot({path:`${process.env.E2E_ARTIFACT_DIR}/appeals-list-${width}.png`,fullPage:false});
 await page.goto(base+'/records?date=2026-10-21&availability=1');
 await page.fill('[name=start_date]','2026-10-21');await page.fill('[name=end_date]','2026-10-21');
 await page.fill('[name=start_time]',width===1440?'10:00':width===1100?'12:00':'14:00');
 await page.fill('[name=end_time]',width===1440?'11:00':width===1100?'13:00':'15:00');
 await Promise.all([page.waitForNavigation(),page.locator('.workflow-availability-form button[type=submit]').click()]);
 await page.goto(base+'/records?date=2026-10-21');
 await page.locator('.workflow-slot a').filter({hasText:'Записать'}).first().click();
 await page.selectOption('[name=apartment_id]',{index:1},{force:true});await page.fill('[name=contact]','Иванов Иван Иванович');await page.fill('[name=contact_phone]','+7 900 000-00-01\n+7 900 000-00-02');
 await Promise.all([page.waitForURL(/records\/\d+$/),page.locator('.workflow-editor button[type=submit]').filter({hasText:'Записать'}).click()]);
 for(const view of ['day','week','month']){
  await page.goto(base+'/records?date=2026-10-21&view='+view);
  assert.ok(await page.locator('.workflow-calendar').isVisible());
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`overflow ${width} ${view}`);
  await page.waitForTimeout(900);
  if(process.env.E2E_ARTIFACT_DIR)await page.screenshot({path:`${process.env.E2E_ARTIFACT_DIR}/records-${view}-${width}.png`,fullPage:false});
 }
 const png=await context.request.get(base+'/records/download?date=2026-10-21');assert.equal(png.status(),200);assert.ok(png.headers()['content-type'].includes('image/png'));
 if(process.env.E2E_ARTIFACT_DIR)fs.writeFileSync(process.env.E2E_ARTIFACT_DIR+'/records-download.png',await png.body());
 assert.deepEqual(errors,[]);console.log('PASS workflows '+width);await context.close();
}
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
