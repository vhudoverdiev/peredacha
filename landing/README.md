# Landing Page

Отдельная стартовая страница для `akvilon-peredacha.ru`.

## Что здесь находится

- [index.html](/C:/Users/Владимир/Desktop/Сайты/Peredacha/landing/index.html) — основной лендинг
- [styles.css](/C:/Users/Владимир/Desktop/Сайты/Peredacha/landing/styles.css) — отдельные стили лендинга
- `assets/` — логотип и favicon для главного домена

CRM при этом остаётся на `lk.akvilon-peredacha.ru`.

## Локальная проверка

1. Запустите статический сервер для лендинга:

```powershell
cd C:\Users\Владимир\Desktop\Сайты\Peredacha\landing
python -m http.server 8080
```

2. Откройте:

```text
http://127.0.0.1:8080
```

3. Если хотите проверить кнопку входа локально, отдельно поднимите CRM:

```powershell
cd C:\Users\Владимир\Desktop\Сайты\Peredacha
venv\Scripts\activate
flask run --host 127.0.0.1 --port 5000
```

На `localhost` и `127.0.0.1` лендинг автоматически отправляет кнопку входа на `http://127.0.0.1:5000/login`.  
На реальном домене кнопки ведут на `https://lk.akvilon-peredacha.ru/login`.

## Как выложить на сервер

Ниже пример для Linux-сервера с `nginx + gunicorn`.

### 1. Разложить файлы

Лендинг:

```bash
sudo mkdir -p /var/www/akvilon-peredacha
sudo rsync -av landing/ /var/www/akvilon-peredacha/landing/
```

CRM:

```bash
sudo mkdir -p /var/www/crm_flask
sudo rsync -av --exclude venv --exclude .git ./ /var/www/crm_flask/
```

### 2. Настроить DNS

Нужны записи:

- `A` для `akvilon-peredacha.ru` -> IP сервера
- `A` для `www.akvilon-peredacha.ru` -> IP сервера
- `A` для `lk.akvilon-peredacha.ru` -> IP сервера

### 3. Подключить nginx

Используйте шаблон [deploy/nginx-akvilon-peredacha.conf](/C:/Users/Владимир/Desktop/Сайты/Peredacha/deploy/nginx-akvilon-peredacha.conf).

Пример:

```bash
sudo cp /var/www/crm_flask/deploy/nginx-akvilon-peredacha.conf /etc/nginx/sites-available/akvilon-peredacha
sudo ln -s /etc/nginx/sites-available/akvilon-peredacha /etc/nginx/sites-enabled/akvilon-peredacha
sudo nginx -t
sudo systemctl reload nginx
```

### 4. Выпустить SSL

После того как DNS уже смотрит на сервер:

```bash
sudo certbot --nginx -d akvilon-peredacha.ru -d www.akvilon-peredacha.ru -d lk.akvilon-peredacha.ru
```

### 5. Проверить gunicorn и CRM

Если CRM уже работает как systemd-сервис:

```bash
sudo systemctl status gunicorn
sudo systemctl restart gunicorn
```

Если у вас сервис называется по-другому, используйте его имя.  
В текущем репозитории уже есть примеры service-файлов в папке `deploy/`.

## Как проверить после выкладки

Откройте:

- `https://akvilon-peredacha.ru` — стартовая страница
- `https://www.akvilon-peredacha.ru` — должен открываться тот же лендинг
- `https://lk.akvilon-peredacha.ru/login` — форма входа в CRM

Проверьте:

- логотип и шрифты загрузились
- кнопка `Перейти в личный кабинет` ведёт на `lk`
- статика CRM на `lk` открывается без `404`
- сертификат выпущен сразу на оба домена и поддомен
