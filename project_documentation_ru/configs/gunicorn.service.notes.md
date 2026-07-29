# Примечания по Gunicorn service

Основной deploy-файл хранится здесь:

```text
deploy/gunicorn.service
```

Важные требования для продакшена:

- запуск от пользователя `www-data`, не от root;
- использование приватного Unix socket;
- автоматический restart;
- чтение переменных окружения из `/opt/peredacha/.env`;
- включение systemd hardening:
  - `NoNewPrivileges=true`;
  - `PrivateTmp=true`;
  - `ProtectSystem=full`;
  - `ProtectHome=true`;
  - `UMask=0077`;
  - лимиты ресурсов.

