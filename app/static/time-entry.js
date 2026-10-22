(() => {
  const ready=new WeakSet();let current=null,id=0;
  const close=()=>{if(!current)return;current.list.remove();current.input.setAttribute('aria-expanded','false');current.button.setAttribute('aria-expanded','false');current=null;};
  function init(){
    document.querySelectorAll('[data-time-field]').forEach(field=>{
      if(ready.has(field))return;ready.add(field);
      const input=field.querySelector('input'),button=field.querySelector('button');
      const listId=`time-options-${++id}`;
      input.setAttribute('role','combobox');input.setAttribute('aria-controls',listId);input.setAttribute('aria-expanded','false');input.setAttribute('aria-autocomplete','list');
      const normalize=()=>{
        const value=input.value.trim().replace('.',':');
        const match=value.match(/^(\d{1,2}):?(\d{2})$/);
        if(match&&+match[1]<24&&+match[2]<60)input.value=`${match[1].padStart(2,'0')}:${match[2]}`;
      };
      input.addEventListener('blur',()=>{normalize();setTimeout(()=>{if(current?.field===field&&!field.contains(document.activeElement)&&!current.list.contains(document.activeElement))close();},0);});
      input.addEventListener('input',()=>{normalize();open(true);});
      const open=(filter=false)=>{
        close();const list=document.createElement('div');list.id=listId;list.className='crm-time-options';list.setAttribute('role','listbox');list.setAttribute('aria-label','Время');
        const minutes=[];for(let minute=0;minute<1440;minute+=Number(field.dataset.timeStep)||15)minutes.push(minute);
        if(!minutes.includes(1439))minutes.push(1439);
        const digits=input.value.replace(/\D/g,'');
        let choices=minutes;
        if(filter&&digits){
          if(digits.length<4) choices=minutes.filter(minute=>`${String(Math.floor(minute/60)).padStart(2,'0')}${String(minute%60).padStart(2,'0')}`.startsWith(digits.length===1&&+digits>2?'0'+digits:digits));
          else if(/^([01]\d|2[0-3]):[0-5]\d$/.test(input.value)){
            const target=Number(input.value.slice(0,2))*60+Number(input.value.slice(3));
            choices=[...new Set([...minutes,target])].sort((a,b)=>Math.abs(a-target)-Math.abs(b-target)).slice(0,8).sort((a,b)=>a-b);
          }else choices=[];
        }
        choices.forEach(minute=>{
          const value=`${String(Math.floor(minute/60)).padStart(2,'0')}:${String(minute%60).padStart(2,'0')}`;
          const option=document.createElement('button');option.type='button';option.textContent=value;option.setAttribute('role','option');
          option.setAttribute('aria-selected',String(input.value===value));
          option.addEventListener('mousedown',event=>event.preventDefault());
          option.addEventListener('click',()=>{input.value=value;input.dispatchEvent(new Event('change',{bubbles:true}));close();input.focus();});
          list.append(option);
        });
        if(!choices.length){const empty=document.createElement('div');empty.textContent='Нет подходящего времени';empty.className='p-2 text-muted';list.append(empty);}
        const rect=field.getBoundingClientRect(),below=innerHeight-rect.bottom-8,above=rect.top-8;
        const height=Math.min(220,Math.max(below,above));
        Object.assign(list.style,{left:`${Math.max(4,rect.left)}px`,width:`${Math.min(rect.width,innerWidth-8)}px`,maxHeight:`${height}px`,top:`${below>=Math.min(220,above)?rect.bottom+4:Math.max(4,rect.top-height-4)}px`});
        document.body.append(list);current={field,list,input,button};input.setAttribute('aria-expanded','true');button.setAttribute('aria-expanded','true');
        list.querySelector('[aria-selected=true]')?.scrollIntoView({block:'nearest'});
      };
      button.addEventListener('click',()=>{if(current?.field===field)close();else open();});
      input.addEventListener('keydown',event=>{if(event.key==='ArrowDown'){event.preventDefault();if(current?.field!==field)open();current.list.querySelector('button')?.focus();}if(event.key==='Escape')close();});
    });
  }
  document.addEventListener('pointerdown',event=>{if(current&&!current.field.contains(event.target)&&!current.list.contains(event.target))close();});
  document.addEventListener('keydown',event=>{
    if(!current)return;
    if(event.key==='Escape'){const input=current.input;close();input.focus();}
    if(['ArrowDown','ArrowUp'].includes(event.key)&&current.list.contains(event.target)){
      event.preventDefault();const options=[...current.list.children],index=options.indexOf(event.target);
      options[(index+(event.key==='ArrowDown'?1:-1)+options.length)%options.length].focus();
    }
  });
  document.addEventListener('submit',close,true);window.addEventListener('resize',close);
  document.addEventListener('scroll',event=>{if(current&&!current.list.contains(event.target))close();},true);
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
  document.addEventListener('crm:ajax-pagination-updated',init);
})();
