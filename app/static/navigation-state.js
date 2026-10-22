// Preserve each browser history entry without replaying form submissions.
(() => {
  const prefix = 'crm-history-v1:';
  const user = document.body.dataset.navigationUser || '0';
  const project = document.body.dataset.navigationProject || '0';
  const identityKey = prefix + 'user';
  try {
    if (sessionStorage.getItem(identityKey) !== user) {
      Object.keys(sessionStorage).filter(key => key.startsWith(prefix)).forEach(key => sessionStorage.removeItem(key));
      sessionStorage.setItem(identityKey, user);
    }
  } catch (_) {}
  if (user === '0') return;
  const scope = `${prefix}${user}:${project}:`;
  const stateKey = 'crmHistoryEntry';
  const newId = () => window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  const uri = () => location.pathname + location.search;
  const originalReplace = history.replaceState.bind(history);
  const originalPush = history.pushState.bind(history);
  let entry = history.state?.[stateKey] || newId();
  let activeUrl = uri();
  let pending = null;
  let restoring = false;
  originalReplace({ ...history.state, [stateKey]: entry }, '', location.href);

  const controls = () => {
    const counts = new Map();
    return Array.from(document.querySelectorAll('input, textarea, select')).flatMap(element => {
      const type = (element.type || '').toLowerCase();
      const name = element.name || element.id;
      if (!name || ['hidden', 'password', 'file', 'submit', 'button', 'reset'].includes(type)) return [];
      if (/password|csrf|token|secret|captcha|two.?factor|otp|verification|code/i.test(name)) return [];
      if (element.autocomplete === 'one-time-code' || element.closest('[data-navigation-private]')) return [];
      const form = element.form;
      // Autosaved controls use the current server value. Restoring an old draft
      // could otherwise write stale data on the next blur/change.
      if ([element, form].some(node => node && (Array.from(node.attributes).some(attribute => /auto.?save/i.test(attribute.name))
          || /auto.?save/i.test(node.className)))) return [];
      const formKey = form?.id || `${form?.getAttribute('action') || ''}:${Array.from(document.forms).indexOf(form)}`;
      const base = `${formKey}:${name}:${type}`;
      const index = counts.get(base) || 0;
      counts.set(base, index + 1);
      return [{ element, key: `${base}:${index}` }];
    });
  };
  const scrolls = () => [document.scrollingElement, ...document.querySelectorAll('.app-content, .objects-content, .documents-content, .documents-standalone-content')].filter(Boolean);
  const save = () => {
    if (restoring || pending) return;
    try {
      if (sessionStorage.getItem(identityKey) !== user) return;
      const fields = controls().map(({ element, key }) => ({ key,
        value: element.multiple ? Array.from(element.selectedOptions, option => option.value) : element.value.slice(0, 20000),
        checked: element.checked,
      }));
      const snapshot = { url: activeUrl, at: Date.now(), fields,
        scroll: scrolls().map(element => [element.scrollLeft, element.scrollTop]) };
      const json = JSON.stringify(snapshot);
      if (json.length > 250000) return;
      const keys = Object.keys(sessionStorage).filter(key => key.startsWith(scope));
      if (keys.length >= 60 && !keys.includes(scope + entry)) {
        keys.sort((a, b) => {
          try { return JSON.parse(sessionStorage.getItem(a)).at - JSON.parse(sessionStorage.getItem(b)).at; } catch (_) { return 0; }
        });
        sessionStorage.removeItem(keys[0]);
      }
      sessionStorage.setItem(scope + entry, json);
    } catch (_) {}
  };
  const read = () => {
    try {
      if (sessionStorage.getItem(identityKey) !== user) return null;
      const saved = JSON.parse(sessionStorage.getItem(scope + entry));
      return saved?.url === uri() && Array.isArray(saved.fields) && Array.isArray(saved.scroll)
        && Date.now() - saved.at < 86400000 ? saved : null;
    } catch (_) { return null; }
  };
  const restore = () => {
    if (!pending || pending.url !== uri()) return;
    restoring = true;
    const fields = new Map(pending.fields.filter(field => typeof field?.key === 'string'
      && (typeof field.value === 'string' || Array.isArray(field.value))).map(field => [field.key, field]));
    controls().forEach(({ element, key }) => {
      const field = fields.get(key);
      if (!field) return;
      if (element.multiple && Array.isArray(field.value)) {
        Array.from(element.options).forEach(option => { option.selected = field.value.includes(option.value); });
      } else element.value = field.value;
      if (['checkbox', 'radio'].includes(element.type)) element.checked = field.checked;
      // Update presentation only. A change event could submit/autosave the form.
      if (element.tagName === 'SELECT') {
        const label = element.closest('.developer-custom-select, .developer-select')?.querySelector('.developer-select-value');
        if (label) label.textContent = element.selectedOptions[0]?.textContent || '';
      }
    });
    scrolls().forEach((element, index) => {
      const position = pending.scroll[index];
      if (position) { element.scrollLeft = position[0]; element.scrollTop = position[1]; }
    });
    restoring = false;
  };
  const queueRestore = () => {
    pending = read();
    if (!pending) return;
    requestAnimationFrame(restore);
    setTimeout(restore, 100);
    setTimeout(restore, 320);
    setTimeout(() => { if (!document.querySelector('.ajax-pagination-loading')) finishRestore(); }, 400);
  };
  const finishRestore = () => { if (pending) { restore(); pending = null; } };
  history.replaceState = (state, title, url) => {
    originalReplace({ ...state, [stateKey]: entry }, title, url);
    activeUrl = uri();
  };
  history.pushState = (state, title, url) => {
    finishRestore();
    entry = newId();
    originalPush({ ...state, [stateKey]: entry }, title, url);
    activeUrl = uri();
    save();
  };
  document.addEventListener('input', event => { if (pending && !event.isTrusted) return; finishRestore(); save(); }, true);
  document.addEventListener('change', event => { if (pending && !event.isTrusted) return; finishRestore(); save(); }, true);
  document.addEventListener('click', () => { finishRestore(); save(); }, true);
  document.addEventListener('pointerdown', finishRestore, true);
  document.addEventListener('wheel', finishRestore, { capture: true, passive: true });
  document.addEventListener('submit', save, true);
  window.addEventListener('pagehide', save);
  window.addEventListener('popstate', event => {
    // The URL already belongs to the destination; save under the outgoing URL.
    save();
    entry = event.state?.[stateKey] || newId();
    activeUrl = uri();
    originalReplace({ ...event.state, [stateKey]: entry }, '', location.href);
    queueRestore();
  });
  window.addEventListener('pageshow', event => {
    const back = performance.getEntriesByType('navigation')[0]?.type === 'back_forward';
    if (event.persisted || back) queueRestore();
  });
  document.addEventListener('crm:ajax-pagination-updated', () => {
    if (pending) requestAnimationFrame(finishRestore);
    else save();
  });
  // Capture scroll positions for page/inner-shell scrolling without overwriting
  // a history entry while its partial-navigation response is still arriving.
  let timer;
  document.addEventListener('scroll', () => {
    clearTimeout(timer);
    timer = setTimeout(save, 100);
  }, true);
})();
