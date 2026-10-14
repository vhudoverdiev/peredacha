#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/peredacha}"
SERVICE_NAME="${SERVICE_NAME:-gunicorn}"
BRANCH="${1:-main}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/.backups}"
DATE_TAG="$(date +%F_%H-%M-%S)"

echo "=== Peredacha deploy started: ${DATE_TAG} ==="

if [ ! -d "$PROJECT_DIR/.git" ]; then
  echo "Ошибка: $PROJECT_DIR не является Git-репозиторием."
  echo "Сначала установи проект через git clone."
  exit 1
fi

mkdir -p "$BACKUP_DIR"
cd "$PROJECT_DIR"

echo "=== Добавляю safe.directory для Git ==="
git config --global --add safe.directory "$PROJECT_DIR" || true

echo "=== Проверяю локальные изменения на сервере ==="
LOCAL_STATUS="$(git status --short || true)"
if [ -n "$LOCAL_STATUS" ]; then
  echo "На сервере есть локальные изменения. Deploy приведет код к версии GitHub:"
  echo "$LOCAL_STATUS"
  if ! git diff --quiet; then
    LOCAL_DIFF_BACKUP="$BACKUP_DIR/local_changes_${DATE_TAG}.patch"
    git diff > "$LOCAL_DIFF_BACKUP" || true
    echo "Бэкап diff локальных правок: $LOCAL_DIFF_BACKUP"
  fi
else
  echo "Локальных изменений на сервере нет."
fi

echo "=== Проверяю изменения на GitHub ==="
git fetch origin "$BRANCH"

LOCAL_COMMIT="$(git rev-parse HEAD)"
REMOTE_COMMIT="$(git rev-parse "origin/$BRANCH")"

echo "Локальная версия: $LOCAL_COMMIT"
echo "Версия GitHub:    $REMOTE_COMMIT"

echo "=== Делаю бэкап важных файлов приложения ==="
if [ -f "$PROJECT_DIR/.env" ]; then
  cp "$PROJECT_DIR/.env" "$BACKUP_DIR/env_${DATE_TAG}.bak"
  echo "Бэкап .env: $BACKUP_DIR/env_${DATE_TAG}.bak"
fi

echo "=== Останавливаю сайт ==="
systemctl --user stop "$SERVICE_NAME" || true

echo "=== Загружаю новую версию с GitHub ==="
git reset --hard "origin/$BRANCH"

echo "=== Удаляю мусор, но сохраняю .env, instance, uploads, exports и venv ==="
git clean -fd \
  -e .env \
  -e instance/ \
  -e uploads/ \
  -e exports/ \
  -e venv/ \
  -e .venv/

echo "=== Cleaning local temporary files ==="
find "$PROJECT_DIR" -maxdepth 1 \( -name '.tmp-*' -o -name '.co?ex' -o -name 'outputs' \) -exec rm -rf {} + 2>/dev/null || true

echo "=== Обновляю системные команды ==="
if [ -f "$PROJECT_DIR/deploy/server-audit.sh" ]; then
  chmod +x "$PROJECT_DIR/deploy/server-audit.sh"
  ln -sf "$PROJECT_DIR/deploy/server-audit.sh" /usr/local/bin/audit-peredacha
  echo "audit-peredacha -> $PROJECT_DIR/deploy/server-audit.sh"
fi
if [ -f "$PROJECT_DIR/audit-peredacha.sh" ]; then
  chmod +x "$PROJECT_DIR/audit-peredacha.sh"
fi

echo "=== Версия после синхронизации с GitHub ==="
git rev-parse --short HEAD
POST_RESET_STATUS="$(git status --short || true)"
if [ -n "$POST_RESET_STATUS" ]; then
  echo "Остались локальные файлы, которые deploy сохранил:"
  echo "$POST_RESET_STATUS"
else
  echo "Git-рабочая копия чистая."
fi

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

echo "=== Проверяю каталоги приложения ==="
mkdir -p "$PROJECT_DIR/instance" "$PROJECT_DIR/uploads" "$PROJECT_DIR/exports"
chmod -R 775 "$PROJECT_DIR/instance" "$PROJECT_DIR/uploads" "$PROJECT_DIR/exports"

echo "=== Запускаю сайт ==="
systemctl --user start "$SERVICE_NAME"
sleep 2

echo "=== Проверяю статус сервиса ==="
if ! systemctl --user is-active --quiet "$SERVICE_NAME"; then
  echo "Ошибка: сервис $SERVICE_NAME не запустился."
  echo "Последние логи:"
  journalctl --user -u "$SERVICE_NAME" -n 80 --no-pager
  exit 1
fi

echo "=== Готово. Сайт обновлён с GitHub. ==="
systemctl --user status "$SERVICE_NAME" --no-pager
