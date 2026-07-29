# Architecture

The application follows a classic Flask server-rendered architecture.

Request flow:

```text
User browser
  -> HTTPS
  -> Nginx reverse proxy
  -> Gunicorn Unix socket
  -> Flask application
  -> SQLAlchemy models
  -> database
```

Main source folders:

- `app/routes.py` - routes, page handlers and business workflows;
- `app/models.py` - SQLAlchemy database models;
- `app/forms.py` - WTForms forms;
- `app/templates/` - Jinja HTML templates;
- `app/static/` - CSS, JavaScript, service worker and static assets;
- `app/services/` - isolated service logic for Excel import/export, PDF, documents, synchronization and task processing;
- `deploy/` - Nginx, Gunicorn and systemd deployment files;
- `tests/` - automated regression and security tests;
- `migrations/` - Alembic/Flask-Migrate files;
- `uploads/` - uploaded files, ignored by Git except `.gitkeep`;
- `exports/` - generated export files, ignored by Git except `.gitkeep`;
- `instance/` - local database/runtime files, ignored by Git.

Main data entities:

- projects/objects;
- apartments and commercial premises;
- users and roles;
- work points;
- tasks/remarks;
- contractors;
- material requests and write-offs;
- glass measurements;
- synchronization logs and conflicts;
- deletion logs;
- security events;
- site visits and error reports.

Access model:

- users authenticate with login and password;
- passwords are stored as salted password hashes, not plaintext;
- roles restrict access to sections and actions;
- users can be limited to specific projects/objects;
- important record access is checked server-side, not only hidden in the interface.

