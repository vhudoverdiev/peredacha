"""Start the workstation copy with local MariaDB; never use production .env."""
import argparse
import getpass
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

from dotenv import dotenv_values
import pymysql
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LOCAL_ENV = ROOT / '.env.local'


def validate_local_database(raw_url):
    try:
        url = make_url(raw_url)
    except (ArgumentError, ValueError):
        raise ValueError('Некорректный DATABASE_URL в .env.local.') from None
    if url.drivername != 'mysql+pymysql':
        raise ValueError('Локальный запуск требует mysql+pymysql.')
    if url.host not in {'localhost', '127.0.0.1', '::1'}:
        raise ValueError('Разрешена только локальная база: localhost или 127.0.0.1.')
    if not url.database or not all(c.isascii() and (c.isalnum() or c == '_') for c in url.database):
        raise ValueError('Некорректное имя локальной базы.')
    if url.query.get('unix_socket') not in {None, '/tmp/mysql.sock'}:
        raise ValueError('Разрешён только локальный сокет /tmp/mysql.sock.')
    return url


def load_local_environment(path=LOCAL_ENV):
    if not path.exists():
        url = URL.create('mysql+pymysql', username=getpass.getuser(), host='localhost',
                         database='peredacha', query={'unix_socket': '/tmp/mysql.sock', 'charset': 'utf8mb4'})
        content = (f"DATABASE_URL='{url.render_as_string(hide_password=False)}'\n"
                   f"SECRET_KEY='{secrets.token_hex(32)}'\n")
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(content)
    values = dotenv_values(path)
    url = validate_local_database(values.get('DATABASE_URL') or '')
    if not values.get('SECRET_KEY'):
        raise ValueError('В .env.local отсутствует SECRET_KEY.')
    # Set these before config.py imports .env. Local settings take precedence.
    environment = {
        'DATABASE_URL': url.render_as_string(hide_password=False),
        'SECRET_KEY': values['SECRET_KEY'],
        'SYNC_ON_STARTUP': 'false',
        'SESSION_COOKIE_SECURE': 'false',
        'REMEMBER_COOKIE_SECURE': 'false',
        'FORCE_HSTS': 'false',
        'TRUSTED_PROXY_COUNT': '0',
        'FLASK_DEBUG': '0',
        'FLASK_SKIP_DOTENV': '1',
        'UPLOAD_FOLDER': str(ROOT / 'uploads'),
        'EXPORT_FOLDER': str(ROOT / 'exports'),
    }
    return url, environment


def connect_local(url, database=True):
    options = dict(user=url.username, password=url.password or '', host=url.host,
                   port=url.port or 3306, charset='utf8mb4', connect_timeout=3, autocommit=True)
    if url.query.get('unix_socket'):
        options['unix_socket'] = url.query['unix_socket']
    if database:
        options['database'] = url.database
    return pymysql.connect(**options)


def ensure_database(url):
    try:
        connection = connect_local(url, database=False)
    except pymysql.err.OperationalError as error:
        if error.args[0] not in {2002, 2003}:
            raise
        brew = shutil.which('brew')
        if not brew:
            brew = next((str(path) for path in (Path('/opt/homebrew/bin/brew'), Path('/usr/local/bin/brew')) if path.exists()), None)
        if not brew:
            raise RuntimeError('MariaDB не запущена. Нужен Homebrew и установленная MariaDB.') from None
        print('Запускаю локальную MariaDB...', flush=True)
        subprocess.run([brew, 'services', 'start', 'mariadb'], check=True)
        connection = None
        for _ in range(30):
            try:
                connection = connect_local(url, database=False)
                break
            except pymysql.err.OperationalError as retry_error:
                if retry_error.args[0] not in {2002, 2003}:
                    raise
                time.sleep(0.5)
        if connection is None:
            raise RuntimeError('MariaDB не запустилась. Проверьте brew services list.')
    with connection:
        with connection.cursor() as cursor:
            # The name was validated; no drops, imports or password changes.
            cursor.execute(f'CREATE DATABASE IF NOT EXISTS `{url.database}` CHARACTER SET utf8mb4')


def main():
    parser = argparse.ArgumentParser(description='Локальная Передача с MariaDB')
    parser.add_argument('--check', action='store_true', help='Проверить запуск без открытия сервера')
    args = parser.parse_args()
    port = int(os.environ.get('PEREDACHA_LOCAL_PORT', '5080'))
    if not 1 <= port <= 65535:
        raise ValueError('PEREDACHA_LOCAL_PORT должен быть от 1 до 65535.')
    url, environment = load_local_environment()
    ensure_database(url)
    os.environ.update(environment)
    from app import create_app
    app = create_app()
    if args.check:
        client = app.test_client()
        for route, mimetype in (('/login', 'text/html'), ('/static/style.css', 'text/css'),
                                ('/static/desktop-only.css', 'text/css'), ('/static/mobile-only.css', 'text/css')):
            response = client.get(route)
            if response.status_code != 200 or response.mimetype != mimetype:
                raise RuntimeError(f'Не прошла проверка {route}: HTTP {response.status_code}')
        print('Локальная MariaDB, страница входа и все три файла стилей: OK.')
        return
    print(f'Передача: http://127.0.0.1:{port}\nБаза: {url.database} (только локальная). Остановка: Ctrl+C.', flush=True)
    app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, pymysql.MySQLError, subprocess.CalledProcessError) as error:
        if isinstance(error, pymysql.MySQLError):
            print(f'Не удалось подключиться к локальной MariaDB (код {error.args[0]}). Проверьте .env.local.', file=sys.stderr)
        else:
            print(str(error), file=sys.stderr)
        sys.exit(1)
