const {webkit}=require('playwright');
(async()=>{
const b=await webkit.launch(),p=await b.newPage({viewport:{width:1100,height:950},deviceScaleFactor:2});
const base='http://127.0.0.1:5197';
await p.goto(base+'/_preview_login/admin');
for(const [key,url,sel] of [
['records','/records?date=2026-11-05','.workflow-page'],
['ocr','/tasks/recognition','.task-recognition-page'],
['avr','/avr?apartment_id=1','#avrDataModal .modal-content'],
['claim','/contractors/excel-selection?contractor_id=1','main'],
['tasks','/assignments?view=issued','main'],
['appeal','/appeals/new','.workflow-page']]){
await p.goto(base+url); await p.waitForTimeout(550);
if(key==='avr') {await p.locator('[data-avr-open-modal]').click();await p.waitForTimeout(400);}
const l=p.locator(sel).first();const box=await l.boundingBox({timeout:1500}).catch(()=>null);
console.log(key,p.url(),box);
const area=box?{x:Math.max(0,box.x),y:Math.max(0,box.y),width:Math.min(box.width,1100-Math.max(0,box.x)),height:Math.min(box.height,key==="claim"?270:key==="tasks"?570:680,950-Math.max(0,box.y))}:{x:260,y:70,width:1150,height:650};
await p.screenshot({path:'.deck-build/'+key+'.png',clip:area});
}
await b.close();
})().catch(e=>{console.error(e);process.exit(1)});
