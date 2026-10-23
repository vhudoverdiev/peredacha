// Explicit suggestions: typing never changes text, point or submitted data.
(() => {
  let nextId = 0;
  const initialized = new WeakSet();
  const bindings = new Map();
  function init(root = document) {
    if (window.matchMedia('(max-width: 767px)').matches) return;
    root.querySelectorAll('[data-remark-suggest]').forEach(field => {
      if (initialized.has(field)) return;
      initialized.add(field);
      const id = `remark-suggestions-${++nextId}`;
      const list = document.createElement('div');
      list.id = id; list.className = 'remark-suggestion-list'; list.hidden = true;
      list.setAttribute('role', 'listbox'); list.setAttribute('aria-label', 'Варианты замечаний');
      const status = document.createElement('div');
      status.className = 'remark-suggestion-status'; status.setAttribute('role', 'status');
      document.body.append(list);
      field.after(status);
      field.setAttribute('role', 'combobox'); field.setAttribute('aria-autocomplete', 'list');
      field.setAttribute('aria-controls', id); field.setAttribute('aria-expanded', 'false');
      field.setAttribute('autocomplete', 'off');
      let items = [], active = -1, timer, controller, generation = 0;
      const close = () => {
        list.hidden = true; active = -1;
        field.setAttribute('aria-expanded', 'false'); field.removeAttribute('aria-activedescendant');
      };
      const position = (reveal = false) => {
        if (list.hidden) return;
        let rect = field.getBoundingClientRect();
        const viewportHeight = window.visualViewport?.height || innerHeight;
        const viewportWidth = document.documentElement.clientWidth;
        if (reveal && viewportHeight - rect.bottom < 106) {
          field.scrollIntoView({block:'center',behavior:'instant'});
          rect = field.getBoundingClientRect();
        }
        const below = viewportHeight - rect.bottom - 10;
        if (rect.bottom < 0 || rect.top > viewportHeight || below < 48) { close(); return; }
        Object.assign(list.style, { left: `${Math.max(8, Math.min(rect.left, viewportWidth - Math.min(rect.width, viewportWidth - 16) - 8))}px`,
          width: `${Math.min(rect.width, viewportWidth - 16)}px`, maxHeight: `${Math.min(250, below)}px`,
          top: `${rect.bottom + 6}px` });
      };
      const onScroll = event => { if (!list.contains(event.target)) position(); };
      const onResize = () => close();
      const onOutside = event => {
        if (event.target !== field && !list.contains(event.target)) {
          generation++; controller?.abort(); clearTimeout(timer); close();
        }
      };
      document.addEventListener('scroll', onScroll, true);
      document.addEventListener('pointerdown', onOutside);
      window.addEventListener('resize', onResize);
      bindings.set(field, () => {
        controller?.abort(); clearTimeout(timer); list.remove();
        document.removeEventListener('scroll', onScroll, true);
        document.removeEventListener('pointerdown', onOutside);
        window.removeEventListener('resize', onResize);
      });
      const fragment = () => {
        const caret = field.selectionStart ?? field.value.length;
        const start = field.value.lastIndexOf('\n', caret - 1) + 1;
        let end = field.value.indexOf('\n', caret);
        if (end < 0) end = field.value.length;
        return { start, end, text: field.value.slice(start, caret).trim() };
      };
      const choose = index => {
        if (!items[index]) return;
        const pointSelect = (field.closest('[data-act-row]')?.querySelector('select[name="act_point"]') || field.form?.querySelector('select[name="point_number"]'));
        const point = items[index].points?.length === 1 ? items[index].points[0].number : null;
        if (pointSelect && point && [...pointSelect.options].some(option => option.value === point)) {
          pointSelect.value = point;
          pointSelect.dispatchEvent(new Event('change', { bubbles: true }));
        }
        const { start, end } = fragment();
        field.setRangeText(items[index].text, start, end, 'end');
        close(); field.focus();
        // Existing form validation, drafts and concession state see the edit.
        field.dispatchEvent(new Event('input', { bubbles: true }));
        clearTimeout(timer); controller?.abort(); generation++;
        status.textContent = '';
      };
      const render = values => {
        list.replaceChildren(); items = values; active = -1;
        values.forEach((item, index) => {
          const option = document.createElement('button');
          option.type = 'button'; option.className = 'remark-suggestion-option';
          option.id = `${id}-${index}`; option.setAttribute('role', 'option');
          option.setAttribute('aria-selected', 'false'); option.tabIndex = -1;
          option.append(document.createTextNode(item.text));
          const point = document.createElement('small');
          point.textContent = item.points.map(p => `${p.number}. ${p.label}`).join(' / ');
          option.append(point);
          option.addEventListener('mousedown', event => event.preventDefault());
          option.addEventListener('click', () => choose(index)); list.append(option);
        });
        list.hidden = !values.length; field.setAttribute('aria-expanded', String(!!values.length));
        status.textContent = '';
        position(true);
      };
      field.addEventListener('input', event => {
        if (event.isComposing) return;
        if (window.matchMedia('(max-width: 767px)').matches) { close(); return; }
        clearTimeout(timer); controller?.abort(); const current = ++generation;
        const part = fragment(); close(); status.textContent = '';
        if (part.text.length < 3 || part.text.length > 500 || field.disabled || field.readOnly) return;
        timer = setTimeout(async () => {
          controller = new AbortController();
          const timeout = setTimeout(() => controller.abort(), 8000);
          try {
            const point = field.dataset.remarkPoint || (field.closest('[data-act-row]')?.querySelector('[name=act_point]') || field.form?.querySelector('[name=point_number]'))?.value || '';
            const params = new URLSearchParams({ q: part.text, point });
            const response = await fetch(`/remarks/suggestions?${params}`, { credentials: 'same-origin',
              cache: 'no-store', signal: controller.signal, headers: { Accept: 'application/json' } });
            if (!response.ok) throw new Error('suggestions-unavailable');
            const payload = await response.json();
            if (current !== generation || !field.isConnected || document.activeElement !== field) return;
            render(Array.isArray(payload.items) ? payload.items : []);
          } catch (error) {
            if (current === generation && error.name !== 'AbortError') {
              close(); status.textContent = 'Подсказки временно недоступны. Можно продолжить ввод вручную.';
            }
          } finally { clearTimeout(timeout); }
        }, 240);
      });
      field.addEventListener('keydown', event => {
        if (event.key === 'Escape') { if (!list.hidden) event.stopPropagation(); generation++; controller?.abort(); clearTimeout(timer); close(); return; }
        if (list.hidden) return;
        if (['ArrowDown', 'ArrowUp'].includes(event.key)) {
          event.preventDefault();
          active = active < 0 ? (event.key === 'ArrowDown' ? 0 : items.length - 1)
            : (active + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
          [...list.children].forEach((el, index) => el.setAttribute('aria-selected', String(index === active)));
          field.setAttribute('aria-activedescendant', `${id}-${active}`);
          const option = list.children[active];
          if (option.offsetTop < list.scrollTop) list.scrollTop = option.offsetTop;
          else if (option.offsetTop + option.offsetHeight > list.scrollTop + list.clientHeight) list.scrollTop = option.offsetTop + option.offsetHeight - list.clientHeight;
        } else if ((event.key === 'Enter' || event.key === 'Tab') && active >= 0) {
          event.preventDefault(); choose(active);
        }
      });
      field.addEventListener('blur', () => setTimeout(() => { if (!list.contains(document.activeElement)) close(); }, 150));
      (field.closest('[data-act-row]')?.querySelector('[name=act_point]') || field.form?.querySelector('[name=point_number]'))?.addEventListener('change', () => {
        generation++; controller?.abort(); clearTimeout(timer); close();
      });
    });
  }
  const cleanup = () => { for (const [field, dispose] of bindings) if (!field.isConnected) { dispose(); bindings.delete(field); } };
  const observe = () => new MutationObserver(cleanup).observe(document.body, { childList: true, subtree: true });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', observe); else observe();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => init());
  else init();
  document.addEventListener('crm:ajax-pagination-updated', () => init());
  document.addEventListener('crm:act-row-added', () => init());
})();
