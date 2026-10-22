const assert=require('node:assert/strict');
const {chromium,webkit}=require('playwright');
const base=process.env.E2E_VISUAL_BASE_URL||'http://127.0.0.1:5098';
(async()=>{
  for(const [engine,width] of [['chromium',1440],['chromium',1024],['webkit',440]]) {
    const browser=await(engine==='webkit'?webkit.launch():chromium.launch({executablePath:process.env.E2E_VISUAL_BROWSER_EXECUTABLE}));
    try {
      const context=await browser.newContext({viewport:{width,height:956},serviceWorkers:'block',isMobile:engine==='webkit',hasTouch:engine==='webkit',
        ...(engine==='webkit'?{userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1'}:{})});
      const page=await context.newPage(),errors=[];
      page.on('pageerror',error=>errors.push(error.message));
      await page.goto(base+'/login');await page.fill('[name=username]','e2e-developer');
      await page.fill('[name=password]','E2E-developer-password-2026!');
      await page.locator('.login-submit').click();await page.waitForURL(url=>!url.pathname.startsWith('/login'));
      await page.goto(base+'/objects/1/open');await page.goto(base+'/apartments/1');
      const csrf=await page.locator('input[name=csrf_token]').first().inputValue();
      const reset=await context.request.post(base+'/apartments/1/inspection-status',{form:{csrf_token:csrf,inspection_status:'not_was'},headers:{Accept:'application/json'}});
      assert.ok(reset.ok());
      await page.reload();
      const details=await page.locator('form.apartment-details-edit-form').evaluate(form=>Object.fromEntries(new FormData(form)));
      for (const mode of ['unsold','app','not_accepted']) {
        const response=await context.request.post(base+'/apartments/1/details',{form:{...details,mode,owner_name:mode==='unsold'?'':details.owner_name},headers:{Accept:'application/json'}});
        assert.ok(response.ok());await page.reload();
        assert.equal(await page.locator('[data-apartment-book-inspection]').count(),mode==='not_accepted'?1:0);
      }
      const booking=page.locator('[data-apartment-book-inspection]');
      assert.equal(await booking.isVisible(),true);
      const form=page.locator('form.apartment-inspection-date-form');
      const buttonBox=await booking.boundingBox(),addBox=await form.locator('button[type=submit]').boundingBox();
      assert.ok(Math.abs(buttonBox.width-addBox.width)<3&&Math.abs(buttonBox.height-addBox.height)<3,JSON.stringify({buttonBox,addBox,styles:await booking.evaluate(el=>{const s=getComputedStyle(el);return {height:s.height,min:s.minHeight,max:s.maxHeight,line:s.lineHeight,transform:s.transform,zoom:s.zoom,box:s.boxSizing};})}));
      const action=await form.getAttribute('action');
      await form.locator('[name=inspection_date]').fill('2030-01-02');
      const updated=page.waitForResponse(response=>response.request().method()==='POST'&&new URL(response.url()).pathname===action);
      await form.locator('button[type=submit]').click();assert.ok([200,302].includes((await updated).status()));
      await page.waitForFunction(()=>document.querySelector('[data-apartment-book-inspection-controls]')?.hidden===true);
      await booking.waitFor({state:'hidden'});
      const removal=page.locator('.apartment-inspection-date-delete-form').filter({has:page.locator('input[name=inspection_date][value="2030-01-02"]')}).first();
      const deleteAction=await removal.getAttribute('action');
      const removed=page.waitForResponse(response=>response.request().method()==='POST'&&new URL(response.url()).pathname===deleteAction);
      await removal.locator('button').click();assert.ok([200,302].includes((await removed).status()));
      await page.waitForFunction(()=>document.querySelector('[data-apartment-book-inspection-controls]')?.hidden===false);
      assert.equal(await booking.isVisible(),true);
      await booking.click();await page.waitForURL('**/records/apartment/1/book');
      assert.deepEqual(errors,[]);
      console.log(`PASS booking visibility, live date change/reset and navigation: ${engine} ${width}`);
      await context.close();
    } finally {await browser.close();}
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
