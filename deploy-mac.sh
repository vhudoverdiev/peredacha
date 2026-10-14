#!/bin/zsh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"
BRANCH="$(git branch --show-current)"

read "CONFIRM?Продолжить deploy? Введите да или нет: "
CONFIRM="${CONFIRM:l}"
if [[ "$CONFIRM" == "нет" || "$CONFIRM" == "no" || "$CONFIRM" == "n" ]]; then
  echo "Деплой отменён."
  exit 0
fi
if [[ "$CONFIRM" != "да" && "$CONFIRM" != "yes" && "$CONFIRM" != "y" ]]; then
  echo "Нужно ввести да или нет. Деплой отменён."
  exit 1
fi

if [[ "${1:-}" == "M" || "${1:-}" == "m" ]]; then
  if [[ -n "$(git status --porcelain)" ]]; then
    git stash push --include-untracked --message "auto-stash before deploy M $(date '+%Y-%m-%d %H:%M:%S')"
    echo "Изменения сохранены. Вернуть их можно командой: git stash pop"
  fi
  git pull --ff-only origin "$BRANCH"
  echo "Готово. Локальные изменения не коммитировались."
  exit 0
fi

if [[ -z "$(git status --porcelain)" ]]; then
  echo "Локальных изменений для отправки нет."
  exit 0
fi

read "COMMIT_MESSAGE?Введите сообщение коммита (Enter — Update local changes): "
COMMIT_MESSAGE="${COMMIT_MESSAGE:-Update local changes}"
git add -A
git commit -m "$COMMIT_MESSAGE"
git push origin "$BRANCH"
echo "Готово: изменения отправлены в GitHub."
