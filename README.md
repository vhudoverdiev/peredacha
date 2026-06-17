# CRM Flask для строительных замечаний

Требуется Python 3.10+ из-за modern type hints и синтаксиса проекта.

Готовый стартовый проект CRM на Flask для объекта «100 Квартал 7 очередь».

Главная идея проекта: Google Sheets или Excel дают структуру и первичные данные, а SQLite хранит CRM-состояние — статусы, выполнение, ответственных, историю изменений и настройки вкладок. Поэтому при новой загрузке таблицы выполненные задачи не сбрасываются.

## Что внутри

- Flask application factory.
- Flask-Login авторизация.
- SQLite + SQLAlchemy + Flask-Migrate.
- Google Sheets API синхронизация.
- Excel импорт/экспорт через openpyxl.
- Уникальный `source_uid` для сопоставления задач.
- Many-to-many связь «вкладка CRM ↔ пункт таблицы».
- Быстрые статусы задач.
- Карточка задачи и история изменений.
- Экспорт задач в Excel.
- Экспорт исходной Excel-таблицы с зачёркнутыми выполненными задачами.
- Gunicorn, Nginx и systemd unit/timer.

## 1. Как распаковать проект

```bash
unzip crm_flask.zip
cd crm_flask
```

## 2. Как создать виртуальное окружение

```bash
python -m venv venv
source venv/bin/activate
```

На Windows:

```powershell
python -m venv venv
venv\Scripts\activate
```

## 3. Как установить зависимости

```bash
pip install -r requirements.txt
```

## 4. Как настроить `.env`

```bash
cp .env.example .env
nano .env
```

Минимально проверьте:

```env
SECRET_KEY=change-this-to-long-random-string
DATABASE_URL=sqlite:///instance/crm.sqlite
GOOGLE_SHEETS_SPREADSHEET_ID=your_spreadsheet_id
GOOGLE_SERVICE_ACCOUNT_JSON=/absolute/path/to/service-account.json
GOOGLE_SHEETS_MAIN_RANGE=Таблица!A1:ZZ10000
```

`GOOGLE_SERVICE_ACCOUNT_JSON` должен быть абсолютным путём к JSON-файлу сервисного аккаунта. Не кладите этот JSON в git-репозиторий.

## 5. Как создать Google Service Account

1. Откройте Google Cloud Console.
2. Создайте проект или выберите существующий.
3. Включите Google Sheets API.
4. Создайте Service Account.
5. Создайте JSON key.
6. Скачайте JSON на сервер.
7. Укажите путь к нему в `.env`.

## 6. Как дать доступ сервисному аккаунту к Google Sheets

1. Откройте вашу Google-таблицу.
2. Нажмите «Настроить доступ» / Share.
3. Скопируйте email сервисного аккаунта из JSON-файла, обычно он выглядит как `name@project.iam.gserviceaccount.com`.
4. Выдайте доступ к таблице.
5. Для чтения достаточно Viewer, для зачёркивания выполненных задач нужен Editor.

## 7. Как запустить локально

```bash
flask db init
flask db migrate -m "Initial migration"
flask db upgrade
python create_admin.py
flask seed-defaults
flask run
```

Откройте:

```text
http://127.0.0.1:5000
```

## 8. Как создать администратора

```bash
python create_admin.py
```

Введите логин, имя и пароль. Пароль хешируется через Werkzeug, в открытом виде не хранится.

## 9. Как запустить синхронизацию с Google Sheets

```bash
flask sync-sheets
```

Или в интерфейсе CRM нажмите кнопку:

```text
Синхронизировать с онлайн-таблицей
```

## 10. Как загрузить новую Excel-таблицу

1. Войдите под `admin` или `manager`.
2. Откройте «Загрузить Excel».
3. Выберите `.xlsx`.
4. CRM прочитает лист, найдёт заголовки, пункты и непустые ячейки замечаний.
5. Новые задачи создадутся со статусом «Не начато».
6. Старые задачи обновятся, но статус «Выполнено» не будет сброшен.
7. Задачи, которых нет в новой таблице, получат флаг `is_missing_in_latest_sync`.

## 11. Как скачать таблицу с зачёркнутыми выполненными

После загрузки Excel нажмите:

```text
Скачать таблицу с зачёркнутыми выполненными
```

CRM возьмёт последний загруженный `.xlsx`, найдёт выполненные задачи по сохранённым координатам ячеек и применит `strike=True` к ячейкам через openpyxl. Остальная структура таблицы сохраняется по возможности.

## 12. Как настроить соответствие пунктов и вкладок

Откройте:

```text
Пункты и вкладки
```

После первой синхронизации появятся реальные пункты из таблицы. Можно отметить, какие пункты входят во вкладки:

- Маляры: 10, 11, 12.
- Разнорабочие: 11, 12, 13, 14, 15, 19, 20.
- Витражники: 16, 17, 18.

Один пункт можно добавить сразу в несколько вкладок.

## 13. Как пользоваться фильтрами, поиском и сортировкой

На странице «Задачи» доступны:

- поиск по квартире, строительному номеру, собственнику, телефону, тексту замечания, пункту и ответственному;
- фильтр по статусу;
- фильтр по ответственному;
- фильтр по пункту таблицы;
- сортировка по квартире, строительному номеру, собственнику, пункту, статусу, приоритету и плановой дате.

Вкладки CRM фильтруют задачи по привязанным пунктам таблицы.

## 14. Как настроить Gunicorn

Скопируйте проект на сервер, например:

```bash
sudo mkdir -p /var/www/crm_flask
sudo rsync -a ./ /var/www/crm_flask/
sudo chown -R www-data:www-data /var/www/crm_flask
cd /var/www/crm_flask
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
flask db upgrade
```

Скопируйте unit-файлы:

```bash
sudo cp deploy/gunicorn.service /etc/systemd/system/
sudo cp deploy/gunicorn.socket /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable gunicorn.socket
sudo systemctl start gunicorn.socket
sudo systemctl status gunicorn.socket
```

## 15. Как настроить Nginx

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/crm_flask
sudo ln -s /etc/nginx/sites-available/crm_flask /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

В `deploy/nginx.conf` замените:

```nginx
server_name crm.example.com;
```

на ваш домен или IP.

## 16. Как настроить systemd

Проверьте пути в файлах `deploy/*.service`:

```text
WorkingDirectory=/var/www/crm_flask
Environment="PATH=/var/www/crm_flask/venv/bin"
EnvironmentFile=/var/www/crm_flask/.env
```

Если проект лежит в другом каталоге — поменяйте пути.

## 17. Как включить автоматическую синхронизацию

```bash
sudo cp deploy/sync-sheets.service /etc/systemd/system/
sudo cp deploy/sync-sheets.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable sync-sheets.timer
sudo systemctl start sync-sheets.timer
sudo systemctl list-timers | grep sync-sheets
```

По умолчанию timer запускает `flask sync-sheets` каждые 30 минут.

## 18. Как экспортировать отчёты в Excel

На странице «Задачи» выставьте нужные фильтры и нажмите:

```text
Экспорт текущего фильтра в Excel
```

CRM выгрузит ровно тот набор задач, который соответствует текущим фильтрам и сортировке.

## Логика `source_uid`

Задача сопоставляется не по номеру строки Excel, потому что строки могут сдвигаться. Ключ строится так:

```text
hash(project_name + construction_number + apartment_number + work_point_number + normalized_remark_text)
```

Нормализация текста:

- нижний регистр;
- удаление лишних пробелов;
- удаление переносов строк;
- единый формат строки.

Если задача уже есть в SQLite, CRM обновляет данные из таблицы, но не сбрасывает `status`, `is_done`, `completed_date`, `manually_edited` и историю изменений.

## Важные файлы

```text
app/services/google_sheets_sync.py  # Google Sheets API
app/services/excel_import.py        # импорт .xlsx
app/services/excel_export.py        # экспорт .xlsx и зачёркивание
app/services/task_service.py        # upsert задач, фильтры, статистика
app/services/uid_service.py         # стабильный source_uid
app/services/mapping_service.py     # вкладки и many-to-many соответствия
```

## Что стоит доработать под реальную таблицу

У разных Excel/Google Sheets могут отличаться заголовки. В проекте уже есть эвристики поиска колонок в `app/services/task_service.py`:

```python
APARTMENT_HEADERS
IGNORED_POINT_HEADER_PARTS
```

Если в вашей таблице заголовки называются иначе, добавьте туда свои варианты. Это нормальная точка адаптации под конкретный файл «100 Квартал 7 очередь».

#   p e r e d a c h a  
 