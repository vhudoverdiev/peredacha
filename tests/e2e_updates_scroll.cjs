const assert=require('node:assert/strict'),path=require('node:path'),{execFileSync}=require('node:child_process');
const{chromium,webkit}=require('playwright');
const base='http://127.0.0.1:5098';
// This modifies only the disposable QA database, never application data.
function seed(body){execFileSync(path.resolve('venv/bin/python'),['-c',`import sqlite3,sys\nc=sqlite3.connect('_codex_chat_files/qa.sqlite');c.execute('delete from developer_updates')\nif sys.argv[1]:c.execute("insert into developer_updates(title,body,published_at,created_at,updated_at) values(?,?,'2026-10-23 10:00:00','2026-10-23 10:00:00','2026-10-23 10:00:00')",('Проверка прокрутки',sys.argv[1]))\nc.commit()`,body]);}
(async()=>{for(const[engine,width]of[['chromium',1440],['chromium',1024],['webkit',440]]){
 const browser=await(engine==='webkit'?webkit.launch():chromium.launch({executablePath:process.env.E2E_VISUAL_BROWSER_EXECUTABLE}));
 try{const page=await browser.newPage({viewport:{width,height:956},serviceWorkers:'block',isMobile:engine==='webkit',hasTouch:engine==='webkit',...(engine==='webkit'?{userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1'}:{})});
 await page.goto(base+'/login');await page.fill('[name=username]','e2e-admin');await page.fill('[name=password]','E2E-visual-password-2026!');await page.locator('.login-submit').click();await page.waitForURL(u=>!u.pathname.startsWith('/login'));
 for(const[kind,body]of[['empty',''],['short','Короткое обновление'],['long',Array(100).fill('Подробное описание изменений CRM.').join('\n')]]){
 seed(body);await page.goto(base+'/updates');await page.locator('.dev-news-history').waitFor();
 const size=await page.evaluate(()=>({viewport:innerHeight,document:document.scrollingElement.scrollHeight,width:document.documentElement.scrollWidth}));
 assert.ok(size.width<=width+1);
 if(width===440&&kind!=='long')assert.ok(size.document<=size.viewport+1,JSON.stringify({kind,size}));
 if(kind==='long'){const nav=page.locator('.dev-news-pagination');await nav.scrollIntoViewIfNeeded();assert.ok(await nav.isVisible());const bottom=await nav.boundingBox();assert.ok(bottom.y>=0&&bottom.y+bottom.height<=956+1);assert.ok(await nav.evaluate(e=>{while(e){if(e.scrollTop>100)return true;e=e.parentElement;}return window.scrollY>100;}));}
 else if(width===440){const back=await page.getByRole('link',{name:'На главную',exact:true}).boundingBox();assert.ok(back.y<150&&back.x<60);}
 await page.screenshot({path:path.resolve(`_codex_chat_files/archive-scroll-${kind}-${engine}-${width}.png`)});
 }
 console.log(`PASS empty/short archive has no extra mobile scroll; long archive remains scrollable: ${engine} ${width}`);
 }finally{await browser.close();}
}seed('');})().catch(e=>{console.error(e);process.exitCode=1;});
