const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
(async()=>{
 const context={self:{navigator:{onLine:true},addEventListener(){}},Response,URL,AbortController,setTimeout,clearTimeout};
 vm.createContext(context);vm.runInContext(fs.readFileSync('app/static/service-worker.js','utf8'),context);
 let calls=0;context.fetch=async()=>{calls++;await new Promise(resolve=>setTimeout(resolve,3300));return new Response('slow success');};
 let response=await context.navigationNetworkFirst('http://crm/');assert.equal(await response.text(),'slow success');assert.equal(calls,1);
 for(const status of [401,403,500,503]){context.fetch=async()=>new Response('server response',{status});assert.equal((await context.navigationNetworkFirst('http://crm/')).status,status);}
 context.fetch=async()=>{throw new TypeError('network failure');};
 response=await context.navigationNetworkFirst('http://crm/');assert.equal(response.headers.get('X-CRM-Mobile-Offline'),'0');assert.ok((await response.text()).includes('<h2>Сервер временно недоступен</h2>'));
 context.self.navigator.onLine=false;response=await context.navigationNetworkFirst('http://crm/');assert.equal(response.headers.get('X-CRM-Mobile-Offline'),'1');assert.ok((await response.text()).includes('<h2>Нет интернета</h2>'));
 console.log('PASS slow navigation >3s, unchanged HTTP errors, server failure vs offline, no automatic retry');
})().catch(e=>{console.error(e);process.exitCode=1;});
