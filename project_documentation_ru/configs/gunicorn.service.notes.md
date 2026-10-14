# Примечания по Gunicorn service

Основной deploy-файл хранится здесь:

```text
deploy/gunicorn.service
```

Важные требования для продакшена:

- запуск от обычного пользователя через `systemctl --user`, без `User=nginx` и `Group=nginx`;
- использование локального TCP-адреса `127.0.0.1:8000`;
- автоматический restart;
- чтение переменных окружения из `/opt/peredacha/.env`;
- включение systemd hardening:
  - `NoNewPrivileges=true`;
  - `PrivateTmp=true`;
  - `ProtectSystem=full`;
  - `ProtectHome=true`;
  - `UMask=0077`;
  - лимиты ресурсов.
