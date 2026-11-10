(() => {
  let state=null;
  const stop=()=>{if(!state)return;clearTimeout(state.expiryTimer);clearInterval(state.pollTimer);state.controller?.abort();state=null;};
  const fallback=()=>{
    const root=state?.root;if(!root)return;
    if(root.hasAttribute('data-news-personal-only')){root.hidden=true;return;}
    const template=root.querySelector('[data-news-fallback]');
    if(template){root.replaceChildren(template.content.cloneNode(true));root.classList.remove('dev-news-personal');delete root.dataset.newsExpires;delete root.dataset.newsVersion;}
  };
  async function refresh(){
    const current=state;if(!current||document.hidden||!navigator.onLine||current.busy)return;
    current.busy=true;current.controller=new AbortController();
    try{
      const response=await fetch(current.root.dataset.newsUrl,{credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'},signal:current.controller.signal});
      if([400,401,403].includes(response.status)){fallback();current.root.hidden=true;stop();return;}
      if(!response.ok)return;
      const data=await response.json();if(state!==current||!current.root.isConnected)return;
      const template=document.createElement('template');template.innerHTML=data.html;
      const next=template.content.querySelector('[data-developer-news]');
      if(!next){current.root.hidden=true;stop();return;}
      if(next.dataset.newsVersion===current.root.dataset.newsVersion){
        current.root.hidden=false;
        current.root.dataset.newsNow=next.dataset.newsNow;
        if(next.dataset.newsExpires)current.root.dataset.newsExpires=next.dataset.newsExpires;
        scheduleExpiry();return;
      }
      current.root.replaceWith(next);init();
    }catch(error){if(error.name!=='AbortError'){/* Keep the last global fallback available offline. */}}
    finally{current.busy=false;}
  }
  function scheduleExpiry(){
    if(!state)return;clearTimeout(state.expiryTimer);state.deadline=null;
    const expires=Date.parse(state.root.dataset.newsExpires),serverNow=Date.parse(state.root.dataset.newsNow);
    if(!Number.isFinite(expires)||!Number.isFinite(serverNow))return;
    // Duration comes from the server; a wrong phone clock cannot extend a message.
    state.deadline=performance.now()+Math.max(0,expires-serverNow);
    state.expiryTimer=setTimeout(()=>{fallback();refresh();},Math.max(0,expires-serverNow));
  }
  function initTimePicker(){
    const dialog=document.getElementById('developer-time-picker');
    if(!dialog?.showModal||dialog.dataset.ready)return;
    const input=document.getElementById('developer-publish-time');
    const trigger=document.querySelector('.dev-news-time-trigger');
    if(!input||!trigger)return;
    dialog.dataset.ready='1';
    const form=dialog.querySelector('form');
    const hours=form.elements.hours;
    const minutes=form.elements.minutes;
    const refreshLabel=()=>{
      trigger.querySelector('[data-time-value]').textContent=input.value||'Выберите время';
      trigger.classList.toggle('is-empty',!input.value);
    };
    const minuteButtons=dialog.querySelectorAll('[data-time-minute]');
    const refreshMinuteButtons=()=>{
      minuteButtons.forEach(button=>button.setAttribute('aria-pressed',
        String(minutes.value!=='' && Number(minutes.value)===Number(button.dataset.timeMinute))));
    };
    trigger.addEventListener('click',()=>{
      [hours.value,minutes.value]=(input.value||'09:00').split(':');
      refreshMinuteButtons();
      dialog.showModal();
    });
    dialog.querySelectorAll('[data-time-close]').forEach(button=>button.addEventListener('click',()=>dialog.close()));
    minuteButtons.forEach(button=>button.addEventListener('click',()=>{
      minutes.value=button.dataset.timeMinute;
      refreshMinuteButtons();
    }));
    minutes.addEventListener('input',refreshMinuteButtons);
    form.addEventListener('submit',event=>{
      event.preventDefault();
      input.value=[hours.value,minutes.value].map(value=>String(Number(value)).padStart(2,'0')).join(':');
      input.dispatchEvent(new Event('change',{bubbles:true}));
      dialog.close();
    });
    dialog.addEventListener('close',()=>trigger.focus({preventScroll:true}));
    input.addEventListener('change',refreshLabel);
    refreshLabel();
    input.hidden=true;
    trigger.hidden=false;
  }

  function init(){
    initTimePicker();
    const root=document.querySelector('[data-developer-news]');if(root===state?.root)return;
    stop();if(!root)return;
    state={root,busy:false};scheduleExpiry();state.pollTimer=setInterval(refresh,60000);
  }
  document.addEventListener('visibilitychange',()=>{if(!document.hidden){if(state?.deadline&&performance.now()>=state.deadline)fallback();refresh();}});
  window.addEventListener('online',refresh);
  window.addEventListener('pageshow',event=>{init();if(event.persisted){fallback();refresh();}});
  document.addEventListener('crm:ajax-pagination-updated',init);
  function start(){init();new MutationObserver(init).observe(document.body,{childList:true,subtree:true});
    document.querySelectorAll('[name=duration_unit]').forEach(select=>{
      const sync=()=>{const input=select.form?.querySelector('[name=duration_value]');if(input)input.max=String(Math.floor(10080/Number(select.value)));};
      select.addEventListener('change',sync);sync();
    });
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();
