(() => {
  let state=null;
  const stop=()=>{if(!state)return;clearTimeout(state.expiryTimer);clearInterval(state.pollTimer);state.controller?.abort();state=null;};
  const fallback=()=>{
    const root=state?.root;if(!root)return;
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
  function init(){
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
