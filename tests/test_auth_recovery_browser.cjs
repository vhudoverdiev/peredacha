const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../app/templates/base.html'), 'utf8');
const code = html.match(/<script>\s*(\/\/ Recover expired AJAX sessions[\s\S]*?)<\/script>/)[1];
async function check({ status = 401, marker = '1', target = '/login?next=%2Fobjects', pathname = '/objects', expected = 1, frame = false } = {}) {
  const redirects = [];
  let calls = 0;
  const response = { status, headers: { get(name) { return name === 'X-CRM-Auth-Required' ? marker : target; } } };
  const location = { origin: 'https://crm.example', pathname, replace: value => redirects.push(value) };
  const window = { location, fetch: async () => { calls++; return response; } };
  window.top = frame ? { location: { replace() { throw new Error('frame blocked'); } } } : window;
  vm.runInNewContext(code, { window, URL });
  for (let i = 0; i < 2; i++) assert.equal(await window.fetch('/objects', { method: 'POST' }), response);
  assert.equal(calls, 2, 'Requests must not be retried');
  assert.equal(redirects.length, expected);
  for (const url of redirects) assert.equal(new URL(url).origin, location.origin);
}
(async () => {
  await check();
  await check({ frame: true });
  await check({ status: 403, expected: 0 });
  await check({ marker: null, expected: 0 });
  await check({ target: 'https://evil.example/login', expected: 0 });
  await check({ target: '/objects', expected: 0 });
  await check({ pathname: '/login', expected: 0 });
  await check({ target: 'http://[', expected: 0 });
  console.log('8 browser authentication recovery cases: OK');
})().catch(error => { console.error(error); process.exitCode = 1; });
