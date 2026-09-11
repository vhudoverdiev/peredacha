# Gunicorn service notes

The deployment service file is stored in:

```text
deploy/gunicorn.service
```

Important production requirements:

- run as `www-data`, not root;
- use a private Unix socket;
- restart automatically;
- read environment variables from `/opt/peredacha/.env`;
- enable systemd hardening:
  - `NoNewPrivileges=true`;
  - `PrivateTmp=true`;
  - `ProtectSystem=full`;
  - `ProtectHome=true`;
  - `UMask=0077`;
  - resource limits.

