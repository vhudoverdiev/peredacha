const assert=require('node:assert/strict');
const path=require('node:path');
const {execFileSync}=require('node:child_process');
const {chromium,webkit}=require('playwright');
const base='http://127.0.0.1:5098';
const database=path.resolve('_codex_chat_files/qa.sqlite');
async function login(page,name,password){await page.goto(base+'/login');await page.fill('[name=username]',name);await page.fill('[name=password]',password);await page.locator('.login-submit').click();await page.waitForURL(url=>!url.pathname.startsWith('/login'));}
(async()=>{
 for(const [engine,width] of [['chromium',1440],['chromium',1024],['webkit',440]]){
  const browser=await(engine==='webkit'?webkit.launch():chromium.launch({executablePath:process.env.E2E_VISUAL_BROWSER_EXECUTABLE}));
  try{
   const options={viewport:{width,height:956},serviceWorkers:'block',isMobile:engine==='webkit',hasTouch:engine==='webkit',...(engine==='webkit'?{userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1'}:{})};
   const admin=await browser.newContext(options),user=await browser.newContext(options);
   const editor=await admin.newPage(),page=await user.newPage(),errors=[];
   editor.on('pageerror',e=>errors.push(e.message));page.on('pageerror',e=>errors.push(e.message));
   await login(editor,'e2e-developer','E2E-developer-password-2026!');
   await editor.goto(base+'/developer/updates');
   assert.equal(await editor.locator('[name=title]').count(),0);
   assert.equal(await editor.getByRole('link',{name:'Отправить',exact:true}).count(),0);
   if(width>767){const nav=await editor.locator('.dev-news-modes').boundingBox(),action=await editor.locator('.dev-news-create').boundingBox();assert.ok(Math.abs(nav.y+nav.height/2-action.y-action.height/2)<2);assert.ok(action.x>nav.x+nav.width);}
   await editor.getByRole('link',{name:'Добавить',exact:true}).click();
   assert.equal(await editor.getByRole('button',{name:'Сохранить черновик',exact:true}).evaluate(el=>getComputedStyle(el).color),'rgb(0, 0, 0)');
   const title=`Обновление ${engine} ${width} ${Date.now()}`,personal=`Спасибо за ошибку ${engine} ${width}`;
   await editor.fill('[name=title]',title);await editor.fill('[name=body]','Исправлены замечания. Добавлены новые возможности для работы с объектом.');
   await editor.getByRole('button',{name:'Опубликовать всем',exact:true}).click();
   await editor.getByRole('heading',{name:title,exact:true}).waitFor();
   for(const name of ['Редактировать','Снять с публикации'])assert.equal(await editor.getByText(name,{exact:true}).first().evaluate(el=>getComputedStyle(el).color),'rgb(0, 0, 0)');
   assert.ok(await editor.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   await editor.waitForFunction(()=>{let node=document.querySelector('.developer-news-page');while(node){if(Number(getComputedStyle(node).opacity)<.999)return false;node=node.parentElement;}return true;});
   await editor.screenshot({path:path.resolve(`_codex_chat_files/developer-editor-${engine}-${width}.png`),fullPage:false});
   await editor.getByRole('link',{name:'Личные сообщения',exact:true}).click();
   assert.equal(await editor.getByRole('link',{name:'Добавить',exact:true}).count(),0);
   await editor.getByRole('link',{name:'Отправить',exact:true}).click();
   const recipient=await editor.locator('[name=recipient_id] option').filter({hasText:'e2e-admin'}).getAttribute('value');
   if(engine==='webkit')await editor.locator('[name=recipient_id]').selectOption(recipient);
   else {
    await editor.locator('[name=recipient_id]').locator('..').locator('.developer-select-button').click();
    const option=editor.locator('.developer-select-menu-portal.is-portal-open .developer-select-option').filter({hasText:'e2e-admin'});
    await option.click();
    assert.equal(await editor.locator('[name=recipient_id]').inputValue(),recipient);
   }
   await editor.fill('[name=title]',personal);await editor.fill('[name=body]','Спасибо за найденную ошибку, мы её исправили. <script>window.__news_xss=1</script>');
   await editor.fill('[name=duration_value]','1');if(engine==='webkit')await editor.locator('[name=duration_unit]').selectOption('1');
   else {await editor.locator('[name=duration_unit]').locator('..').locator('.developer-select-button').click();await editor.locator('.developer-select-menu-portal.is-portal-open .developer-select-option').filter({hasText:'Минуты'}).click();}
   await editor.getByRole('button',{name:'Отправить пользователю',exact:true}).click();
   await editor.getByText('Ожидает первого показа',{exact:true}).first().waitFor();
   await login(page,'e2e-admin','E2E-visual-password-2026!');await page.goto(base+'/');
   await page.locator('.dev-news-personal').waitFor();
   assert.equal(await page.locator('.dev-news-personal-badge').count(),1);
   assert.equal(await page.locator('.dev-news-brand').first().evaluate(el=>getComputedStyle(el).borderTopLeftRadius),'13px');
   assert.equal(await page.locator('.dev-news-personal').evaluate(el=>getComputedStyle(el).borderLeftColor),'rgb(219, 149, 28)');assert.ok((await page.locator('[data-developer-news]').textContent()).includes('Худовердиев В')); assert.ok((await page.locator('[data-developer-news]').textContent()).includes(personal));
   assert.equal(await page.evaluate(()=>window.__news_xss),undefined);
   await page.locator('[data-developer-news]').scrollIntoViewIfNeeded();
   await page.screenshot({path:path.resolve(`_codex_chat_files/developer-personal-${engine}-${width}.png`),fullPage:false});
   // Only the disposable QA database: shorten the already-started receipt to exercise real expiry without waiting a minute.
   execFileSync(path.resolve('venv/bin/python'),['-c',"import sqlite3,sys;from datetime import datetime,timedelta,timezone;c=sqlite3.connect(sys.argv[1]);c.execute('UPDATE developer_personal_messages SET expires_at=? WHERE title=?',((datetime.now(timezone.utc).replace(tzinfo=None)+timedelta(seconds=4)).strftime('%Y-%m-%d %H:%M:%S.%f'),sys.argv[2]));c.commit();c.close()",database,personal]);
   await page.reload();await page.locator('.dev-news-personal').waitFor();
   assert.equal(await page.locator('.dev-news-personal-badge').count(),1);
   assert.equal(await page.locator('.dev-news-brand').first().evaluate(el=>getComputedStyle(el).borderTopLeftRadius),'13px');
   assert.equal(await page.locator('.dev-news-personal').evaluate(el=>getComputedStyle(el).borderLeftColor),'rgb(219, 149, 28)');assert.ok((await page.locator('[data-developer-news]').textContent()).includes('Худовердиев В')); 
   await user.setOffline(true);
   let navigations=0;page.on('framenavigated',()=>navigations++);
   await page.locator('.dev-news-personal').waitFor({state:'detached',timeout:10000});
   await page.locator('[data-developer-news] h2').filter({hasText:title}).waitFor();
   assert.equal(navigations,0);assert.ok(!(await page.locator('[data-developer-news]').textContent()).includes(personal));
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   await page.locator('[data-developer-news]').scrollIntoViewIfNeeded();
   await page.screenshot({path:path.resolve(`_codex_chat_files/developer-global-${engine}-${width}.png`),fullPage:false});
   await user.setOffline(false);
   await page.getByRole('link',{name:/Посмотреть все/}).click();await page.waitForURL('**/updates');
   assert.ok((await page.locator('.dev-news-history').textContent()).includes(title));
   assert.ok(!(await page.locator('.dev-news-history').textContent()).includes(personal));
   await editor.goto(base+'/developer/updates?mode=messages');
   for(const [name,label] of [[personal,'Удалить личное сообщение'],[title,'Удалить обновление']]){
    if(label==='Удалить обновление')await editor.goto(base+'/developer/updates');
    const article=editor.locator('article').filter({has:editor.getByRole('heading',{name,exact:true})});
    const trash=article.getByRole('button',{name:label,exact:true});
    assert.equal(await trash.evaluate(el=>getComputedStyle(el).color),'rgb(196, 60, 60)');
    await trash.click();await editor.locator('.js-crm-confirm-modal:not(.d-none)').waitFor();
    await editor.locator('.js-crm-confirm-cancel').click();assert.equal(await article.count(),1);
    await trash.click();await editor.locator('.js-crm-confirm-ok').click();
    await article.waitFor({state:'detached'});
   }
   await page.goto(base+'/updates');assert.ok(!(await page.locator('.dev-news-history').textContent()).includes(title));
   assert.deepEqual(errors,[]);
   console.log(`PASS publication, private delivery, expiry without reload, archive and mobile layout: ${engine} ${width}`);
   await admin.close();await user.close();
  }finally{await browser.close();}
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
