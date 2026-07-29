# Automated tests

The project contains automated tests in the `tests/` directory.

Current test coverage includes:

- authorization and login behavior;
- roles and access restrictions;
- protection against IDOR-style access to records from other projects;
- CSRF behavior;
- XSS escaping;
- SQL injection regression checks;
- file upload validation;
- Excel import/export behavior;
- report generation;
- apartment cards and apartment details;
- material requests and write-offs;
- glass measurement/order workflows;
- delete confirmation modals;
- Firefox layout regressions;
- service worker/cache behavior;
- deployment/security configuration contracts.

Recommended command:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests
```

Last full local verification during the security audit:

```text
Ran 497 tests
OK
```

Additional checks used:

```powershell
.\venv\Scripts\python.exe -m pip check
.\venv\Scripts\pip-audit.exe --path .\venv\Lib\site-packages
node --check app/static/script.js
node --check app/static/service-worker.js
```

