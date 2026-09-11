# Peredacha CRM

CRM для контроля передачи помещений: замечания, задачи, исполнители, материалы, документы и АВР в одном месте.

## Возможности

- загрузка Excel-таблиц по объектам;
- автоматическое создание замечаний и задач;
- дашборд по квартирам, коммерции и отделке;
- назначение исполнителей и контроль выполненных работ;
- экспорт замечаний в Excel с отдельными вкладками выполненных и невыполненных;
- учет расхода материалов с распределением по квартирам;
- формирование АВР по шаблону Word;
- журналы загрузок, синхронизаций и удалений.

## Быстрый старт

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
flask db upgrade
python create_admin.py
flask run
```

После запуска откройте:

```text
http://127.0.0.1:5000
```

## Настройка

Создайте `.env` на основе `.env.example` и проверьте основные параметры:

```env
SECRET_KEY=change-this-to-long-random-string
DATABASE_URL=sqlite:///instance/crm.sqlite
```

Если используется Google Sheets, дополнительно укажите ID таблицы и путь к JSON сервисного аккаунта.

## Основные разделы

- **Объекты** - загрузка таблиц и переход к работе по объекту.
- **Замечания** - список дефектов, статусы, фильтры и Excel-экспорт.
- **Выдача задач** - назначение, смена и снятие исполнителей.
- **Расход материалов** - списание материалов по выбранным квартирам.
- **АВР** - формирование акта выполненных работ по шаблону.
- **Документы** - хранение и выгрузка рабочих файлов.

## Стек

Flask, SQLAlchemy, Flask-Login, Flask-Migrate, SQLite, openpyxl, python-docx.

## Полезные команды

```powershell
flask db migrate -m "Описание изменений"
flask db upgrade
flask seed-defaults
```

## Структура

```text
app/routes.py                 # маршруты и бизнес-логика
app/models.py                 # модели базы данных
app/services/excel_import.py  # импорт Excel
app/services/excel_export.py  # экспорт Excel
app/services/avr_document.py  # генерация АВР
app/templates/                # HTML-шаблоны
app/static/                   # стили и JavaScript
```
