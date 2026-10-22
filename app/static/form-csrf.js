// Refresh only before an explicit submission; never retry a rejected POST.
(() => {
  const prepared = new WeakSet();
  const pending = new WeakSet();
  document.addEventListener('submit', async event => {
    const form = event.target;
    if (!form.matches?.('form[data-refresh-csrf]')) return;
    if (prepared.has(form)) { prepared.delete(form); return; }
    event.preventDefault();
    event.stopImmediatePropagation();
    if (pending.has(form)) return;
    if (!form.checkValidity()) { form.reportValidity(); return; }
    const submitter = event.submitter;
    const buttons = Array.from(form.querySelectorAll('[type="submit"]')).filter(button => !button.disabled);
    pending.add(form);
    buttons.forEach(button => { button.disabled = true; });
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    let leaving = false;
    const abortOnHide = () => { leaving = true; controller.abort(); };
    window.addEventListener('pagehide', abortOnHide, { once: true });
    let submitted = false;
    try {
      const response = await fetch('/csrf-token', { credentials: 'same-origin', cache: 'no-store',
        signal: controller.signal, headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' } });
      if (!response.ok) throw new Error('csrf-refresh-failed');
      const payload = await response.json();
      if (leaving || !form.isConnected) throw new Error('csrf-form-detached');
      if (typeof payload.csrf_token !== 'string' || !payload.csrf_token) throw new Error('csrf-token-missing');
      const fields = form.querySelectorAll('input[name="csrf_token"]');
      if (!fields.length) throw new Error('csrf-field-missing');
      fields.forEach(field => { field.value = payload.csrf_token; });
      buttons.forEach(button => { button.disabled = false; });
      prepared.add(form);
      form.requestSubmit(submitter || undefined);
      submitted = true;
      // Invalid forms do not dispatch submit, so do not retain a stale permit.
      prepared.delete(form);
    } catch (_) {
      if (leaving) return;
      const message = 'Не удалось обновить защитный токен. Данные формы сохранены. Повторите отправку.';
      if (window.showCrmNotice) window.showCrmNotice(message, 'warning');
      else {
        const notice = form.querySelector('[data-csrf-notice]') || document.createElement('p');
        notice.dataset.csrfNotice = '1'; notice.setAttribute('role', 'alert');
        notice.textContent = message; form.prepend(notice);
      }
    } finally {
      clearTimeout(timer);
      window.removeEventListener('pagehide', abortOnHide);
      pending.delete(form);
      if (!submitted) buttons.forEach(button => { button.disabled = false; });
    }
  }, true);
})();
