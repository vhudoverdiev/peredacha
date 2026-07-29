# Configuration

Runtime configuration is controlled through environment variables.

The real `.env` file is not included in this documentation package because it may contain secrets.

Safe example:

```env
FLASK_APP=wsgi.py
FLASK_ENV=production
FLASK_DEBUG=0
SECRET_KEY=replace-with-a-strong-random-secret
DATABASE_URL=postgresql://peredacha_app:replace-password@127.0.0.1:5432/peredacha

GOOGLE_SHEETS_SPREADSHEET_ID=your_spreadsheet_id
GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/service-account.json
GOOGLE_SHEETS_MAIN_RANGE=Таблица!A1:ZZ10000

SYNC_ON_STARTUP=false
SYNC_INTERVAL_MINUTES=30

UPLOAD_FOLDER=uploads
EXPORT_FOLDER=exports
SESSION_COOKIE_SECURE=true
FORCE_HSTS=true
TRUSTED_PROXY_COUNT=1
MAX_CONTENT_LENGTH=52428800
MAX_UPLOAD_FILE_BYTES=26214400
PROTECTED_DEVELOPER_USERNAMES=developer
```

Important security-related settings:

- `SECRET_KEY` must be long, random and unique;
- `FLASK_DEBUG=0` in production;
- `SESSION_COOKIE_SECURE=true` when HTTPS is used;
- `FORCE_HSTS=true` for production HTTPS;
- `TRUSTED_PROXY_COUNT=1` when Flask is behind one trusted Nginx proxy;
- upload and request size limits should stay enabled.

Files and folders that must not be shared publicly:

- `.env`;
- `instance/*.sqlite`;
- uploaded user files;
- generated exports;
- private service account JSON files;
- database backups.

