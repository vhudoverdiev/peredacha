const assert = require('node:assert/strict');
const path = require('node:path');
const { webkit } = require('playwright');
const {execFileSync}=require('node:child_process');
function seedArchive(body){execFileSync(path.resolve('venv/bin/python'),['-c',`import sqlite3,sys\nc=sqlite3.connect('_codex_chat_files/qa.sqlite');c.execute('delete from developer_updates')\nif sys.argv[1]:c.executemany("insert into developer_updates(title,body,published_at,created_at,updated_at) values(?,?,'2026-10-23 10:00:00','2026-10-23 10:00:00','2026-10-23 10:00:00')", [('Обновление CRM',sys.argv[1])]*2)\nc.commit()`,body]);}
const base = process.env.E2E_VISUAL_BASE_URL || 'http://127.0.0.1:5098';
(async () => {
  const browser = await webkit.launch();
  try {
    for (const standalone of [false, true]) {
      const context = await browser.newContext({ viewport: { width: 440, height: 956 },
        screen: { width: 440, height: 956 }, isMobile: true, hasTouch: true,
        deviceScaleFactor: 3, userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1' });
      try {
        if (standalone) await context.addInitScript(() => {
          Object.defineProperty(navigator, 'standalone', { get: () => true });
          Object.defineProperty(screen, 'height', { get: () => 956 });
          Object.defineProperty(screen, 'availHeight', { get: () => 956 });
        });
        const page = await context.newPage();
        await page.goto(base + '/login');
        await page.fill('[name=username]', 'e2e-developer');
        await page.fill('[name=password]', 'E2E-developer-password-2026!');
        await page.locator('.login-submit').click();
        await page.waitForURL(url => !url.pathname.startsWith('/login'));
        await page.goto(base + '/objects/1/open');
        for (const height of [956, 820]) {
          await page.setViewportSize({ width: 440, height });
          await page.goto(base + '/tasks');
          const reference = await page.locator('.mobile-bottom-nav').boundingBox();
          for (const [route, name] of [['/records?date=2080-01-01', 'records'], ['/appeals?q=__no_matches__', 'appeals-empty'], ['/appeals/new', 'appeal-form'], ['/updates', 'archive-empty'], ['/updates', 'archive-filled'], ['/updates', 'archive-long']]) {
            if(name.startsWith('archive-'))seedArchive(name==='archive-empty'?'':name==='archive-filled'?'Улучшена стабильность CRM.':Array(100).fill('Подробное описание обновлений CRM.').join('\n'));
            await page.goto(base + route);
            if (standalone) await page.waitForFunction(() => parseFloat(document.documentElement.style.getPropertyValue('--mobile-physical-app-height')) === 956);
            const dock = page.locator('.mobile-bottom-nav');
            const geometry = await dock.boundingBox();
            // The standalone canvas retains screen.height when iOS shortens innerHeight.
            const expectedBottom = standalone ? 956 : height;
            assert.equal(geometry.height, reference.height);
            assert.equal(geometry.width, reference.width);
            assert.ok(Math.abs(geometry.y + geometry.height - expectedBottom) < 2, JSON.stringify(geometry));
            if (standalone) {
              const content = page.locator('.app-content');
              const box = await content.boundingBox();
              assert.ok((await page.locator('.workflow-page, .dev-news-archive').boundingBox()).x >= 12);
              assert.ok(Math.abs(box.y + box.height - geometry.y) < 2, JSON.stringify({ box, geometry }));
              await content.evaluate(element => { element.scrollTop = element.scrollHeight; });
              assert.deepEqual(await dock.boundingBox(), geometry);
              const last = await page.locator('.workflow-page, .dev-news-archive').evaluate(element => element.getBoundingClientRect().bottom);
              assert.ok(last <= geometry.y, JSON.stringify({ last, geometry }));
              assert.equal(await page.evaluate(() => window.scrollY || document.body.scrollTop), 0);
            } else {
              assert.ok(Math.abs(geometry.y - reference.y) < 2);
            }
            if (height === 956 && process.env.E2E_ARTIFACT_DIR) {
              if (standalone) await page.locator('.app-content').evaluate(element => { element.scrollTop = 0; });
              await page.screenshot({ path: path.join(process.env.E2E_ARTIFACT_DIR, `webkit-${name}-${standalone ? 'app' : 'web'}.png`) });
            }
            console.log(`PASS WebKit dock: ${standalone ? 'standalone' : 'web'} ${height} ${name}`);
          }
        }
      } finally { await context.close(); }
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
