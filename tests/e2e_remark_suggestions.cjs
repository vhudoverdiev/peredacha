const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium, webkit } = require('playwright');
const base = process.env.E2E_VISUAL_BASE_URL || 'http://127.0.0.1:5098';
(async () => {
  for (const [engine, width] of [['chromium',1440], ['chromium',1024], ['webkit',440]]) {
    const browser = await (engine === 'webkit' ? webkit.launch() : chromium.launch({ executablePath:process.env.E2E_VISUAL_BROWSER_EXECUTABLE }));
    try {
      const context = await browser.newContext({ viewport:{width,height:956}, isMobile:engine==='webkit', hasTouch:engine==='webkit',
        serviceWorkers:'block', ...(engine==='webkit' ? {userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1'} : {}) });
      const page = await context.newPage(), errors=[];
      page.on('pageerror', e => errors.push(e.message));
      await page.goto(base+'/login');
      await page.fill('[name=username]','e2e-developer');
      await page.fill('[name=password]','E2E-developer-password-2026!');
      await page.locator('.login-submit').click(); await page.waitForURL(url=>!url.pathname.startsWith('/login'));
      await page.goto(base+'/objects/1/open');
      if(engine==='webkit') {
        await page.goto(base+'/account');
        assert.equal(await page.locator('a[href="/developer/remark-review"]').count(),0);
        assert.equal((await context.request.get(base+'/developer/remark-review')).status(),404);
        await page.goto(base+'/tasks/new?mode=manual&kind=act');
        const field=page.locator('[data-act-row] textarea');
        assert.equal(await field.getAttribute('data-remark-suggest'),null);
        await field.fill('регулировка ПВХ');
        assert.equal(await page.locator('.remark-suggestion-list').count(),0);
        assert.equal(await field.inputValue(),'регулировка ПВХ');
        assert.deepEqual(errors,[]);
        console.log('PASS mobile: no review entry, direct access blocked, manual typing without suggestions');
        await context.close();
        continue;
      }
      await page.goto(base+'/site-errors');
      assert.equal(await page.getByText('Сверка замечаний',{exact:true}).count(),0);
      const response=await context.request.get(base+'/developer/remark-review');
      assert.equal(response.status(),404);
      await page.goto(base+'/tasks/new?mode=manual&kind=single');
      const single=page.locator('[name=description]');
      await single.fill('регулировка'); await single.focus();
      const singleOption=page.locator('.remark-suggestion-option').first();
      await singleOption.waitFor();
      const expectedPoint=(await singleOption.locator('small').textContent()).match(/^(\d+)\./)[1];
      await singleOption.click();
      assert.equal(await page.locator('select[name=point_number]').inputValue(),expectedPoint);
      await page.goto(base+'/tasks/new?mode=manual&kind=act');
      assert.equal(await page.locator('[data-act-row]').count(),1);
      await page.locator('[data-act-add]').click();
      assert.equal(await page.locator('[data-act-row]').count(),2);
      assert.equal(await page.locator('[data-act-remove]').count(),0);
      await page.locator('[data-act-row] select').first().selectOption('17',{force:true});
      const field=page.locator('[data-act-row] textarea').first();
      await field.fill('регулиров');
      await field.focus();
      const list=page.locator('#'+await field.getAttribute('aria-controls'));
      await list.locator('[role=option]').first().waitFor();
      await list.scrollIntoViewIfNeeded();
      await page.screenshot({path:path.resolve(`_codex_chat_files/remark-completion-${engine}-${width}.png`),fullPage:false});
      assert.equal(await field.inputValue(),'регулиров');
      if(width===1440) {
        await field.press('ArrowDown'); await field.press('Enter');
      } else await list.locator('[role=option]').first().click();
      assert.ok((await field.inputValue()).length>10);
      await field.fill('Первая строка сохранена\nрегулиров'); await field.focus();
      await list.locator('[role=option]').first().waitFor();
      await list.locator('[role=option]').first().click();
      assert.ok((await field.inputValue()).startsWith('Первая строка сохранена\n'));
      await field.fill('регулиров'); await field.focus();
      await list.locator('[role=option]').first().waitFor(); await field.press('Escape');
      assert.equal(await field.getAttribute('aria-expanded'),'false');
      await page.route('**/remarks/suggestions?**',route=>route.fulfill({status:503,body:'Unavailable'}));
      await field.fill('регулировка ПВХ'); await field.focus();
      await page.getByText('Подсказки временно недоступны.',{exact:false}).waitFor();
      assert.equal(await field.inputValue(),'регулировка ПВХ');
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      assert.deepEqual(errors,[]);
      console.log(`PASS removed review, explicit completion, keyboard, network failure: ${engine} ${width}`);
      await context.close();
    } finally { await browser.close(); }
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
