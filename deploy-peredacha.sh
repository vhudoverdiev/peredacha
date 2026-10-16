#!/usr/bin/env bash
set -Eeuo pipefail


PROJECT_DIR="${PROJECT_DIR:-/opt/peredacha}"
SERVICE_NAME="${SERVICE_NAME:-gunicorn}"
BRANCH="${1:-main}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups/peredacha}"
LOCAL_BIN="${LOCAL_BIN:-$HOME/.local/bin}"
DATE_TAG="$(date +%F_%H-%M-%S)"

echo "=== Peredacha deploy started: ${DATE_TAG} ==="

mkdir -p "$BACKUP_DIR" "$LOCAL_BIN"
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
systemctl --user stop "$SERVICE_NAME" || true

echo "=== Удаляю временные SQLite-файлы после остановки сайта ==="
find "$PROJECT_DIR/instance" -maxdepth 1 -type f \( -name '*.sqlite-shm' -o -name '*.sqlite-wal' \) -delete 2>/dev/null || true

echo "=== Загружаю новую версию с GitHub ==="
git reset --hard "origin/$BRANCH"

echo "=== Удаляю мусор, но сохраняю .env, базу, uploads, exports и venv ==="
git clean -fd \
  -e .env \
  -e instance/ \
  -e uploads/ \
  -e exports/ \
  -e venv/ \
  -e .venv/ \
  -e .pycache/

echo "=== Cleaning local temporary files ==="
find "$PROJECT_DIR" -maxdepth 1 \( -name '.tmp-*' -o -name '.co?ex' -o -name 'outputs' \) -exec rm -rf {} + 2>/dev/null || true

echo "=== Обновляю пользовательские команды (~/.local/bin) ==="
if [ -f "$PROJECT_DIR/deploy/server-audit.sh" ]; then
  chmod +x "$PROJECT_DIR/deploy/server-audit.sh"
  ln -sf "$PROJECT_DIR/deploy/server-audit.sh" "$LOCAL_BIN/audit-peredacha"
  echo "audit-peredacha -> $PROJECT_DIR/deploy/server-audit.sh"
  case ":$PATH:" in
    *":$LOCAL_BIN:"*) ;;
    *) echo "Подсказка: добавь $LOCAL_BIN в PATH (в ~/.bashrc или ~/.profile), иначе команда audit-peredacha не найдётся." ;;
  esac
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
export PYTHONPYCACHEPREFIX="$PROJECT_DIR/.pycache"
mkdir -p "$PYTHONPYCACHEPREFIX"
python -m compileall -q app

echo "=== Проверяю Flask-приложение и базу ==="
python - <<'PY'
from app import create_app, db
app = create_app()
with app.app_context():
    db.create_all()
print("Flask app OK, database OK")
PY

echo "=== Выставляю права (без chown, всё уже принадлежит текущему пользователю) ==="
mkdir -p "$PROJECT_DIR/instance" "$PROJECT_DIR/uploads" "$PROJECT_DIR/exports"
chmod -R u+rwX "$PROJECT_DIR/instance" "$PROJECT_DIR/uploads" "$PROJECT_DIR/exports"

echo "=== Запускаю сайт (user systemd unit) ==="
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