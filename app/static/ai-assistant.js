(() => {
  'use strict';
  window.crmAiCleanup?.();
  const dialog = document.getElementById('crm-ai-dialog');
  if (!dialog) return;
  const messages = document.getElementById('crm-ai-messages');
  const form = document.getElementById('crm-ai-form');
  const input = document.getElementById('crm-ai-question');
  const send = document.getElementById('crm-ai-send');
  const status = document.getElementById('crm-ai-status');
  let reportMode = false;
  let initialized = false;
  let nextSendAt = 0;
  let trigger, busy = false, faq = [], pendingInfo, disposed = false, epoch = 0;
  const welcomeTemplate = messages.firstElementChild.cloneNode(true);
  const controllers = new Set();
  function node(tag, text, cls) {
    const el = document.createElement(tag);
    if (text) el.textContent = text;
    if (cls) el.className = cls;
    return el;
  }
  async function request(url, options = {}) {
    const controller = new AbortController(); controllers.add(controller);
    const timeout = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(url, {...options, credentials:'same-origin', cache:'no-store', signal:controller.signal,
        headers:{Accept:'application/json', 'X-Requested-With':'XMLHttpRequest', ...options.headers}});
      const data = response.headers.get('Content-Type')?.includes('application/json') ? await response.json() : {};
      if(response.ok && !Object.keys(data).length)throw new Error('Сессия завершилась. Обновите страницу и войдите снова.');
      if (!response.ok) throw new Error(data.error || data.message || 'Не удалось получить ответ. Повторите попытку.');
      return data;
    } finally {clearTimeout(timeout);controllers.delete(controller);}
  }
  function buttons(items) {
    const box = node('div', null, 'crm-ai-suggestions');
    for (const item of items) {const b=node('button',item.question);b.type='button';b.dataset.aiQuestion=item.question;box.append(b);}
    return box;
  }
  async function info() {
    if (pendingInfo) return pendingInfo;
    const ticket=epoch;
    const flight=request(dialog.dataset.infoUrl).then(data => {
      if (!disposed && ticket===epoch) {faq=data.faqs;const welcome=document.getElementById('crm-ai-welcome');if(welcome)welcome.replaceChildren(buttons(faq.slice(0,3)));}
    }).finally(()=>{if(pendingInfo===flight)pendingInfo=null;});
    pendingInfo=flight;
    return flight;
  }
  function resetChat() {
    epoch++;controllers.forEach(c=>c.abort());controllers.clear();pendingInfo=null;
    busy=false;reportMode=false;input.maxLength=1000;send.disabled=false;faq=[];status.textContent='';status.classList.remove('is-error');
    input.value='';input.style.height='auto';messages.replaceChildren(welcomeTemplate.cloneNode(true));messages.scrollTop=0;
    const ticket=epoch;info().catch(e=>{if(ticket===epoch)error(e);});
  }
  function error(e) {if(!disposed){status.textContent=e.name==='AbortError'?'Ответ задерживается. Попробуйте ещё раз.':e.message;status.classList.add('is-error');}}
  function open(button) {if(!dialog.open){trigger=button;if(!initialized){resetChat();initialized=true;}dialog.showModal();}document.getElementById('crm-ai-close').focus({preventScroll:true});}
  function close() {dialog.close();trigger?.focus({preventScroll:true});}
  function append(el) {messages.append(el);while(messages.children.length>21)messages.firstElementChild.remove();messages.scrollTop=messages.scrollHeight;}
  async function ask(question) {
    question=question.trim();if(busy||!question)return;
    if(Date.now()<nextSendAt){status.textContent='Подождите 2 секунды перед следующим сообщением.';return;}
    nextSendAt=Date.now()+2000;
    if(reportMode){await sendReport(question);return;}
    const ticket=epoch;
    document.getElementById('crm-ai-intro')?.remove();
    busy=true;send.disabled=true;status.classList.remove('is-error');status.textContent='Подбираю ответ…';
    append(node('article',question,'crm-ai-message crm-ai-user'));input.value='';input.style.height='auto';
    try {
      // The server rechecks current permissions for every answer, including follow-ups.
      const answer=await request(dialog.dataset.askUrl,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':form.elements.csrf_token.value},body:JSON.stringify({question})});
      if(disposed||ticket!==epoch)return;
      const el=node('article',null,'crm-ai-message');el.append(node('span','AI АГЕНТ','crm-ai-label'),node('h3',answer.title));
      const list=node(answer.found?'ol':'div');for(const step of answer.steps)list.append(node(answer.found?'li':'p',step));el.append(list);
      if(answer.related?.length){el.append(node('p',answer.found?'Также может пригодиться':'Возможно, вы имели в виду','crm-ai-related'),buttons(answer.related));}
      if(!answer.found){const contact=node('button','Задать вопрос разработчику','crm-ai-report');contact.type='button';contact.dataset.aiReport='question';contact.dataset.question=question;el.append(contact);}
      append(el);status.textContent='';
    } catch(e){if(!disposed&&ticket===epoch){error(e);input.value=question;}}
    finally{if(ticket===epoch){busy=false;send.disabled=false;}}
  }
  async function showFaq() {
    const ticket=epoch;
    try {await info();if(disposed||ticket!==epoch)return;const el=node('article',null,'crm-ai-message crm-ai-faq-list');el.append(node('h3','Частые вопросы'));
      for(const group of new Set(faq.map(i=>i.group))){const details=node('details');details.append(node('summary',group),buttons(faq.filter(i=>i.group===group)));el.append(details);}
      if(!faq.length)el.append(node('p','Напишите вопрос о работе в CRM.'));
      append(el);el.scrollIntoView({block:'start'});
    }catch(e){if(ticket===epoch)error(e);}
  }
  const onClick=e=>{const launch=e.target.closest('[data-ai-open]');if(launch)open(launch);};
  document.addEventListener('click',onClick);
  document.getElementById('crm-ai-close').addEventListener('click',close);
  dialog.addEventListener('cancel',e=>{e.preventDefault();close();});
  document.getElementById('crm-ai-faq').addEventListener('click',showFaq);
  function startReport(question = '') {
    if(busy)return;
    reportMode=true;input.maxLength=5000;
    document.getElementById('crm-ai-intro')?.remove();
    append(node('article','Опишите проблему: что вы делали и что произошло. Отправьте сообщение здесь — его получит разработчик.','crm-ai-message'));
    input.value=question;input.dispatchEvent(new Event('input'));input.focus();
  }
  async function sendReport(message) {
    const ticket=epoch;busy=true;send.disabled=true;status.textContent='Отправляю сообщение…';status.classList.remove('is-error');
    try {
      const body=new URLSearchParams({message,page_url:location.href,csrf_token:form.elements.csrf_token.value});
      const result=await request(dialog.dataset.reportUrl,{method:'POST',body});
      if(disposed||ticket!==epoch)return;
      append(node('article',message,'crm-ai-message crm-ai-user'));
      append(node('article',result.message,'crm-ai-message'));
      input.value='';input.style.height='auto';reportMode=false;input.maxLength=1000;status.textContent='';
    }catch(e){if(!disposed&&ticket===epoch)error(e);}
    finally{if(ticket===epoch){busy=false;send.disabled=false;}}
  }
  messages.addEventListener('click',e=>{const contact=e.target.closest('[data-ai-report]');if(contact){startReport(contact.dataset.question||'');return;}const b=e.target.closest('[data-ai-question]');if(b){reportMode=false;input.maxLength=1000;ask(b.dataset.aiQuestion);}});

  form.addEventListener('submit',e=>{e.preventDefault();ask(input.value);});
  input.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();form.requestSubmit();}});
  input.addEventListener('input',()=>{input.style.height='auto';input.style.height=Math.min(input.scrollHeight,90)+'px';});
  window.crmAiCleanup=()=>{disposed=true;controllers.forEach(c=>c.abort());document.removeEventListener('click',onClick);if(dialog.open)dialog.close();};
})();
