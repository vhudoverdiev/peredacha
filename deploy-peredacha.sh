#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/var/www/crm_flask}"
SERVICE_NAME="${SERVICE_NAME:-gunicorn}"
BRANCH="${1:-main}"
BACKUP_DIR="${BACKUP_DIR:-/root/backups/peredacha}"
DATE_TAG="$(date +%F_%H-%M-%S)"

echo "=== Peredacha deploy started: ${DATE_TAG} ==="

if [ "$(id -u)" -ne 0 ]; then
  echo "Запусти от root или через sudo: sudo deploy-peredacha"
  exit 1
fi

if [ ! -d "$PROJECT_DIR/.git" ]; then
  echo "Ошибка: $PROJECT_DIR не является Git-репозиторием."
  echo "Сначала установи проект через git clone."
  exit 1
fi

mkdir -p "$BACKUP_DIR"
cd "$PROJECT_DIR"

echo "=== Добавляю safe.directory для Git ==="
git config --global --add safe.directory "$PROJECT_DIR" || true

echo "=== Проверяю изменения на GitHub ==="
git fetch origin "$BRANCH"

LOCAL_COMMIT="$(git rev-parse HEAD)"
REMOTE_COMMIT="$(git rev-parse "origin/$BRANCH")"

echo "Локальная версия: $LOCAL_COMMIT"
echo "Версия GitHub:    $REMOTE_COMMIT"

echo "=== Делаю бэкап важных данных ==="
if [ -f "$PROJECT_DIR/instance/crm.sqlite" ]; then
  cp "$PROJECT_DIR/instance/crm.sqlite" "$BACKUP_DIR/crm_${DATE_TAG}.sqlite"
  echo "Бэкап базы: $BACKUP_DIR/crm_${DATE_TAG}.sqlite"
else
  echo "База crm.sqlite пока не найдена, пропускаю бэкап базы."
fi

if [ -f "$PROJECT_DIR/.env" ]; then
  cp "$PROJECT_DIR/.env" "$BACKUP_DIR/env_${DATE_TAG}.bak"
  echo "Бэкап .env: $BACKUP_DIR/env_${DATE_TAG}.bak"
fi

echo "=== Останавливаю сайт ==="
systemctl stop "$SERVICE_NAME" || true

echo "=== Загружаю новую версию с GitHub ==="
git reset --hard "origin/$BRANCH"

echo "=== Удаляю мусор, но сохраняю .env, базу, uploads, exports и venv ==="
git clean -fd \
  -e .env \
  -e instance/ \
  -e uploads/ \
  -e exports/ \
  -e venv/ \
  -e .venv/

echo "=== Обновляю зависимости ==="
if [ ! -d "$PROJECT_DIR/venv" ]; then
  python3 -m venv "$PROJECT_DIR/venv"
fi

source "$PROJECT_DIR/venv/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn

echo "=== Проверяю Python-файлы ==="
python -m compileall -q app

echo "=== Проверяю Flask-приложение и базу ==="
python - <<'PY'
from app import create_app, db
app = create_app()
with app.app_context():
    db.create_all()
print("Flask app OK, database OK")
PY

echo "=== Выставляю права ==="
mkdir -p "$PROJECT_DIR/instance" "$PROJECT_DIR/uploads" "$PROJECT_DIR/exports"
chown -R www-data:www-data "$PROJECT_DIR"
chmod -R 775 "$PROJECT_DIR/instance" "$PROJECT_DIR/uploads" "$PROJECT_DIR/exports"

echo "=== Запускаю сайт ==="
systemctl start "$SERVICE_NAME"
sleep 2

echo "=== Проверяю статус сервиса ==="
if ! systemctl is-active --quiet "$SERVICE_NAME"; then
  echo "Ошибка: сервис $SERVICE_NAME не запустился."
  echo "Последние логи:"
  journalctl -u "$SERVICE_NAME" -n 80 --no-pager
  exit 1
fi

echo "=== Проверяю Nginx ==="
nginx -t
systemctl reload nginx

echo "=== Готово. Сайт обновлён с GitHub. ==="
systemctl status "$SERVICE_NAME" --no-pager
