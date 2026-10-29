// Keep the authenticated shell mounted; each page owns its listeners and observers.
(() => {
  if(document.body.dataset.navigationUser==='0')return;
  const nativeAdd=EventTarget.prototype.addEventListener,nativeRemove=EventTarget.prototype.removeEventListener;
  const nativeTimeout=window.setTimeout.bind(window),nativeInterval=window.setInterval.bind(window);
  const NativeObserver=window.MutationObserver,nativeFetch=window.fetch.bind(window);
  let listeners=[],observers=[],timeouts=new Set(),intervals=new Set(),ready=[],loading=false,controller,serial=0;
  const sourceCache=new Map();
  const persistent=(target,type,handler,options)=>nativeAdd.call(target,type,handler,options);
  EventTarget.prototype.addEventListener=function(type,handler,options){
    if(loading&&((this===document&&type==='DOMContentLoaded')||(this===window&&type==='load'))){ready.push([this,type,handler]);return;}
    listeners.push([this,type,handler,typeof options==='boolean'?options:Boolean(options?.capture)]);
    return nativeAdd.call(this,type,handler,options);
  };
  window.MutationObserver=class extends NativeObserver {constructor(callback){super(callback);observers.push(this);}};
  window.setTimeout=(handler,delay,...args)=>{const id=nativeTimeout(()=>{timeouts.delete(id);if(typeof handler==='function')handler(...args);},delay);timeouts.add(id);return id;};
  window.setInterval=(handler,delay,...args)=>{const id=nativeInterval(handler,delay,...args);intervals.add(id);return id;};
  function dispose(){
    window.crmOfflineDispose?.();
    for(const [target,type,handler,capture]of listeners)nativeRemove.call(target,type,handler,capture);
    listeners=[];observers.forEach(observer=>observer.disconnect());observers=[];
    timeouts.forEach(clearTimeout);intervals.forEach(clearInterval);timeouts.clear();intervals.clear();ready=[];
    document.querySelectorAll('.modal').forEach(node=>window.bootstrap?.Modal.getInstance(node)?.dispose());
  }
  function allowed(url){
    return url.origin===location.origin&&/^https?:$/.test(url.protocol)
      && !/\/(?:logout|login|export|download)(?:\/|$)/.test(url.pathname);
  }
  async function source(script){
    if(!script.src)return script.textContent;
    const url=new URL(script.getAttribute('src'),location.href);
    if(url.origin!==location.origin)throw new Error('External page script');
    if(!sourceCache.has(url.href))sourceCache.set(url.href,nativeFetch(url.href,{credentials:'same-origin'}).then(response=>{if(!response.ok)throw new Error('Page script unavailable');return response.text();}).catch(error=>{sourceCache.delete(url.href);throw error;}));
    return sourceCache.get(url.href);
  }
  async function navigate(href,{push=true}={}){
    const url=new URL(href,location.href);if(!allowed(url)){location.assign(url.href);return;}
    window.crmPageLoading=true;
    const ticket=++serial;controller?.abort();controller=new AbortController();
    const content=document.querySelector('.app-content,.objects-content,.documents-content');content?.setAttribute('aria-busy','true');
    try{
      const response=await nativeFetch(url.href,{credentials:'same-origin',cache:'no-store',signal:controller.signal,headers:{Accept:'text/html','X-Requested-With':'XMLHttpRequest'}});
      if(response.status===401){location.assign('/login');return;}
      if(!response.ok)throw new Error('Не удалось открыть раздел. Повторите попытку.');
      const html=await response.text(),next=new DOMParser().parseFromString(html,'text/html'),finalUrl=new URL(response.url||url.href);
      if(response.headers.get('X-CRM-Worker-Offline')==='1'){window.__CRM_WORKER_OFFLINE__=true;window.__CRM_OFFLINE_FALLBACK__=true;}
      if(next.body.dataset.navigationUser!==document.body.dataset.navigationUser){location.assign(finalUrl.href);return;}
      const scripts=[...next.body.querySelectorAll('script')].filter(script=>!script.src||!/(?:page-navigation|navigation-state)\.js(?:\?|$)/.test(script.src));
      const codes=await Promise.all(scripts.map(source));if(ticket!==serial)return;
      // Preserve the visible chrome, but copy server-rendered active states and labels.
      const selectors=['.app-sidebar','.app-topbar','.mobile-project-topbar','.mobile-app-topbar','.mobile-bottom-nav-root'];
      const retained=[], mounted=new Map([[next.body,document.body]]);
      for(const selector of selectors){const old=document.querySelector(selector),replacement=next.querySelector(selector);if(old&&replacement&&!retained.some(node=>node.contains(old))){
        // Preserve the shell node itself; descendants receive the destination markup.
        old.innerHTML=replacement.innerHTML;for(const attr of [...old.attributes])old.removeAttribute(attr.name);for(const attr of replacement.attributes)old.setAttribute(attr.name,attr.value);
        // Preserve the shared ancestors as well as the shell node: moving
        // either into a detached document drops the browser paint layer.
        let incoming=replacement,current=old;
        while(incoming&&current&&incoming!==next.body&&current!==document.body){
          if(mounted.has(incoming))break;
          mounted.set(incoming,current);incoming=incoming.parentElement;current=current.parentElement;
        }
        retained.push(old);
      }}
      dispose();loading=true;
      next.body.querySelectorAll('script').forEach(script=>script.remove());
      const hasSidebar=next.documentElement.classList.contains('desktop-shell-with-sidebar');
      document.documentElement.classList.toggle('desktop-shell-with-sidebar',hasSidebar);
      const scale=parseFloat(document.documentElement.style.getPropertyValue('--desktop-stage-scale'))||1;
      document.documentElement.style.setProperty('--desktop-shell-sidebar-visual-width',`${hasSidebar?230*scale:0}px`);
      document.documentElement.style.setProperty('--desktop-shell-topbar-visual-height',`${(hasSidebar?78.4:92)*scale}px`);
      document.body.className=next.body.className;
      for(const attr of [...next.body.attributes])if(attr.name!=='class')document.body.setAttribute(attr.name,attr.value);
      function updateMounted(incoming){
        const current=mounted.get(incoming);
        if(retained.includes(current))return current;
        if(current!==document.body){
          for(const attr of [...current.attributes])if(!incoming.hasAttribute(attr.name))current.removeAttribute(attr.name);
          for(const attr of incoming.attributes)current.setAttribute(attr.name,attr.value);
        }
        const children=[...incoming.childNodes].map(child=>mounted.has(child)?updateMounted(child):child);
        // Remove obsolete siblings first; whitespace from parsed HTML must
        // never cause an already mounted shell node to be moved.
        const keep=new Set(children);
        for(const child of [...current.childNodes])if(!keep.has(child))child.remove();
        let cursor=current.firstChild;
        for(const child of children){
          if(child===cursor)cursor=cursor.nextSibling;
          else current.insertBefore(child,cursor);
        }
        while(cursor){const remove=cursor;cursor=cursor.nextSibling;remove.remove();}
        return current;
      }
      updateMounted(next.body);
      document.title=next.title;
      for(const sheet of next.head.querySelectorAll('link[rel=stylesheet]')){
        const href=sheet.getAttribute('href');if(![...document.head.querySelectorAll('link[rel=stylesheet]')].some(node=>node.getAttribute('href')===href))document.head.append(document.importNode(sheet,true));
      }
      if(push)history.pushState({crmShell:true},'',finalUrl.pathname+finalUrl.search+finalUrl.hash);
      for(let i=0;i<codes.length;i++){
        let scriptError;
        const captureError=event=>{scriptError=event.error||new Error(event.message);};
        persistent(window,'error',captureError);
        const script=document.createElement('script');script.textContent=`(() => {\n${codes[i]}\n})();`;document.body.append(script);script.remove();nativeRemove.call(window,'error',captureError);if(scriptError)throw scriptError;
      }
      while(ready.length){const callbacks=ready;ready=[];for(const[target,type,handler]of callbacks){const event=new Event(type);if(typeof handler==='function')handler.call(target,event);else handler?.handleEvent(event);}}
      loading=false;
      document.querySelectorAll('.app-content,.objects-content,.documents-content').forEach(node=>node.scrollTop=0);window.scrollTo(0,0);
      window.crmPageLoading=false;document.dispatchEvent(new CustomEvent('crm:navigation-ready',{detail:{restore:!push}}));
    }catch(error){
      if(error.name==='AbortError')return;
      if(loading){loading=false;location.assign(url.href);return;}
      if(window.showCrmNotice)window.showCrmNotice(error.message,'danger');else window.alert(error.message);
    }finally{if(ticket===serial)window.crmPageLoading=false;if(ticket===serial)document.querySelectorAll('[aria-busy=true]').forEach(node=>node.removeAttribute('aria-busy'));}
  }
  window.crmNavigate=navigate;
  persistent(window,'click',event=>{
    const link=event.target.closest?.('a[href]');if(!link||event.defaultPrevented||event.button!==0||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey||link.hasAttribute('download')||link.dataset.downloadMode||link.hasAttribute('data-bs-toggle')||link.getAttribute('href')?.startsWith('#')||link.target&&link.target!=='_self')return;
    const url=new URL(link.href,location.href);if(!allowed(url)||url.pathname===location.pathname&&url.search===location.search&&url.hash)return;
    event.preventDefault();void navigate(url.href);
  });
  persistent(window,'submit',event=>{
    const form=event.target;
    if(event.defaultPrevented||!(form instanceof HTMLFormElement)||form.method.toLowerCase()!=='get'||form.target&&form.target!=='_self')return;
    const url=new URL(form.action||location.href,location.href);if(!allowed(url))return;
    event.preventDefault();url.search='';
    for(const [name,value]of new FormData(form))if(typeof value==='string')url.searchParams.append(name,value);
    if(event.submitter?.name)url.searchParams.append(event.submitter.name,event.submitter.value);
    void navigate(url.href);
  });
  persistent(window,'popstate',event=>{event.stopImmediatePropagation();void navigate(location.href,{push:false});});
})();
