const {webkit}=require('playwright');
(async()=>{
 const b=await webkit.launch(),p=await b.newPage({viewport:{width:1100,height:950},deviceScaleFactor:2});
 const base='http://127.0.0.1:5197';
 await p.goto(base+'/_preview_login/admin');await p.goto(base+'/report');
 const report=p.locator('.work-report-page');await report.locator('summary').first().click();
 const box=await report.boundingBox();await p.screenshot({path:'.deck-build/report.png',clip:{...box,height:Math.min(box.height,320)}});
 console.log(await report.locator('details').first().innerText());await b.close();
})().catch(e=>{console.error(e);process.exit(1)});
