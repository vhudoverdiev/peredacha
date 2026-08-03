#!/usr/bin/env bash
set -Eeuo pipefail

# Server access audit helper for Peredacha.
# Run on the server:
#   sudo bash deploy/server-audit.sh
# Optional:
#   sudo bash deploy/server-audit.sh --user vladimir --days 14

AUDIT_USER="${AUDIT_USER:-vladimir}"
DAYS="${DAYS:-30}"
LOGIN_LIMIT="${LOGIN_LIMIT:-200}"
HISTORY_LIMIT="${HISTORY_LIMIT:-120}"
TIMEZONE="${TIMEZONE:-Europe/Moscow}"
SINCE_DATE=""

usage() {
  cat <<'EOF'
Использование:
  sudo ./audit-peredacha.sh
  sudo ./audit-peredacha.sh --user vladimir --days 30
  sudo audit-peredacha

Параметры:
  --user ИМЯ            Пользователь для подробного разбора. По умолчанию: vladimir
  --days ЧИСЛО          Сколько последних дней смотреть. По умолчанию: 30
  --since YYYY-MM-DD    Смотреть начиная с конкретной даты
  --login-limit ЧИСЛО   Сколько строк входов показывать. По умолчанию: 200
  --history-limit ЧИСЛО Сколько команд из истории показывать. По умолчанию: 120
  --help                Показать эту справку

Что показывает:
  1. Кто успешно подключался на сервер: аккаунт, IP, время в МСК.
  2. Кто пытался войти неуспешно: аккаунт, IP, время в МСК.
  3. Отдельно по выбранному пользователю: IP входов, sudo-команды,
     shell history и, если включено, process accounting.

Важно:
  Linux не всегда хранит полную историю "что делал пользователь".
  Самые надежные источники: sudo-логи, auditd, process accounting и shell history
  с включенными временными метками. Если они не включены заранее, старые действия
  можно восстановить только частично.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --user)
      AUDIT_USER="${2:-}"
      shift 2
      ;;
    --days)
      DAYS="${2:-}"
      shift 2
      ;;
    --since)
      SINCE_DATE="${2:-}"
      shift 2
      ;;
    --login-limit)
      LOGIN_LIMIT="${2:-}"
      shift 2
      ;;
    --history-limit)
      HISTORY_LIMIT="${2:-}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Неизвестный параметр: $1"
      usage
      exit 1
      ;;
  esac
done

if ! [[ "$DAYS" =~ ^[0-9]+$ ]]; then
  echo "Ошибка: --days должен быть числом."
  exit 1
fi

if [ -z "$SINCE_DATE" ]; then
  SINCE_DATE="$(date -d "${DAYS} days ago" +%F)"
fi

if ! SINCE_EPOCH="$(date -d "$SINCE_DATE 00:00:00" +%s 2>/dev/null)"; then
  echo "Ошибка: --since должен быть датой в формате YYYY-MM-DD."
  exit 1
fi

if ! [[ "$LOGIN_LIMIT" =~ ^[0-9]+$ ]] || ! [[ "$HISTORY_LIMIT" =~ ^[0-9]+$ ]]; then
  echo "Ошибка: лимиты должны быть числами."
  exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

AUTH_EVENTS="$TMP_DIR/auth-events.tsv"
SUDO_EVENTS="$TMP_DIR/sudo-events.tsv"
: > "$AUTH_EVENTS"
: > "$SUDO_EVENTS"

print_section() {
  printf '\n%s\n' "============================================================"
  printf '%s\n' "$1"
  printf '%s\n' "============================================================"
}

print_subsection() {
  printf '\n%s\n' "--- $1 ---"
}

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

msk_now() {
  TZ="$TIMEZONE" date '+%Y-%m-%d %H:%M:%S %Z'
}

to_msk_from_epoch() {
  local epoch="$1"
  TZ="$TIMEZONE" date -d "@$epoch" '+%Y-%m-%d %H:%M:%S %Z' 2>/dev/null || printf '%s' "$epoch"
}

syslog_ts_to_msk() {
  local month="$1"
  local day="$2"
  local time_part="$3"
  local year
  year="$(date +%Y)"
  TZ="$TIMEZONE" date -d "${month} ${day} ${time_part} ${year}" '+%Y-%m-%d %H:%M:%S %Z' 2>/dev/null \
    || printf '%s %s %s' "$month" "$day" "$time_part"
}

syslog_ts_to_epoch() {
  local month="$1"
  local day="$2"
  local time_part="$3"
  local year
  year="$(date +%Y)"
  date -d "${month} ${day} ${time_part} ${year}" '+%s' 2>/dev/null || printf ''
}

journal_ts_to_msk() {
  local raw_ts="$1"
  TZ="$TIMEZONE" date -d "$raw_ts" '+%Y-%m-%d %H:%M:%S %Z' 2>/dev/null || printf '%s' "$raw_ts"
}

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

explain_command() {
  local raw="$1"
  local cmd
  cmd="$(trim "$raw")"

  if [ -z "$cmd" ]; then
    printf 'Пустая команда.'
    return
  fi

  if [[ "$cmd" == sudo\ * ]]; then
    cmd="${cmd#sudo }"
  fi

  case "$cmd" in
    "apt update"|"apt-get update")
      printf 'Обновлял список пакетов системы.'
      ;;
    apt\ install*|apt-get\ install*)
      printf 'Устанавливал системные пакеты: %s' "$raw"
      ;;
    apt\ upgrade*|apt-get\ upgrade*)
      printf 'Обновлял установленные системные пакеты.'
      ;;
    apt\ remove*|apt-get\ remove*|apt\ purge*|apt-get\ purge*)
      printf 'Удалял системные пакеты: %s' "$raw"
      ;;
    systemctl\ status*)
      printf 'Проверял статус службы: %s' "$raw"
      ;;
    systemctl\ restart*)
      printf 'Перезапускал службу: %s' "$raw"
      ;;
    systemctl\ start*)
      printf 'Запускал службу: %s' "$raw"
      ;;
    systemctl\ stop*)
      printf 'Останавливал службу: %s' "$raw"
      ;;
    systemctl\ reload*)
      printf 'Перезагружал конфигурацию службы без полного рестарта: %s' "$raw"
      ;;
    journalctl*)
      printf 'Смотрел системные логи: %s' "$raw"
      ;;
    nginx\ -t*)
      printf 'Проверял конфигурацию Nginx.'
      ;;
    nginx\ *)
      printf 'Выполнял команду Nginx: %s' "$raw"
      ;;
    certbot*)
      printf 'Работал с SSL-сертификатами через Certbot: %s' "$raw"
      ;;
    ufw*)
      printf 'Менял или проверял firewall UFW: %s' "$raw"
      ;;
    git\ status*)
      printf 'Проверял состояние Git-репозитория.'
      ;;
    git\ pull*)
      printf 'Загружал свежие изменения проекта из Git.'
      ;;
    git\ fetch*)
      printf 'Проверял новые изменения в Git без применения.'
      ;;
    git\ reset*)
      printf 'Сбрасывал состояние Git-репозитория: %s' "$raw"
      ;;
    git\ checkout*|git\ switch*)
      printf 'Переключал ветку или версию проекта: %s' "$raw"
      ;;
    git\ log*)
      printf 'Смотрел историю Git-коммитов.'
      ;;
    docker\ compose\ up*|docker-compose\ up*)
      printf 'Запускал контейнеры Docker Compose: %s' "$raw"
      ;;
    docker\ compose\ down*|docker-compose\ down*)
      printf 'Останавливал контейнеры Docker Compose.'
      ;;
    docker\ compose\ logs*|docker-compose\ logs*|docker\ logs*)
      printf 'Смотрел логи Docker-контейнеров: %s' "$raw"
      ;;
    docker\ ps*)
      printf 'Смотрел список Docker-контейнеров.'
      ;;
    docker*)
      printf 'Работал с Docker: %s' "$raw"
      ;;
    flask\ db\ upgrade*)
      printf 'Применял миграции базы данных Flask.'
      ;;
    flask*)
      printf 'Запускал Flask-команду проекта: %s' "$raw"
      ;;
    python*manage.py*|python3*manage.py*)
      printf 'Запускал Django/manage.py команду: %s' "$raw"
      ;;
    python*|python3*)
      printf 'Запускал Python-команду или скрипт: %s' "$raw"
      ;;
    pip\ install*|pip3\ install*)
      printf 'Устанавливал Python-зависимости: %s' "$raw"
      ;;
    cd\ *)
      printf 'Переходил в папку: %s' "${raw#cd }"
      ;;
    ls|ls\ *)
      printf 'Смотрел список файлов и папок.'
      ;;
    pwd)
      printf 'Проверял текущую папку.'
      ;;
    cat\ *|less\ *|more\ *|head\ *|tail\ *)
      printf 'Просматривал содержимое файлов или логов: %s' "$raw"
      ;;
    nano\ *|vim\ *|vi\ *)
      printf 'Редактировал файл: %s' "$raw"
      ;;
    mkdir\ *)
      printf 'Создавал папку: %s' "$raw"
      ;;
    rm\ *)
      printf 'Удалял файлы или папки: %s' "$raw"
      ;;
    cp\ *)
      printf 'Копировал файлы или папки: %s' "$raw"
      ;;
    mv\ *)
      printf 'Перемещал или переименовывал файлы/папки: %s' "$raw"
      ;;
    chmod\ *)
      printf 'Менял права доступа: %s' "$raw"
      ;;
    chown\ *)
      printf 'Менял владельца файлов или папок: %s' "$raw"
      ;;
    ssh\ *)
      printf 'Подключался по SSH дальше с этого сервера: %s' "$raw"
      ;;
    scp\ *|rsync\ *)
      printf 'Копировал файлы между серверами: %s' "$raw"
      ;;
    tar\ *|zip\ *|unzip\ *)
      printf 'Работал с архивами: %s' "$raw"
      ;;
    grep\ *|rg\ *|find\ *)
      printf 'Искал текст или файлы: %s' "$raw"
      ;;
    ps\ *|top|htop|free\ *|df\ *|du\ *)
      printf 'Проверял процессы, память или место на диске: %s' "$raw"
      ;;
    *)
      printf 'Выполнил команду: %s' "$raw"
      ;;
  esac
}

collect_auth_from_journal() {
  if ! has_cmd journalctl; then
    return 0
  fi

  { TZ="$TIMEZONE" journalctl -t sshd -t sudo --since "$SINCE_DATE 00:00:00" --no-pager -o short-iso 2>/dev/null || true; } \
    | while IFS= read -r line; do
        [ -n "$line" ] || continue
        if [[ "$line" =~ ^([^[:space:]]+)[[:space:]]+.*sshd.*Accepted[[:space:]]+([^[:space:]]+)[[:space:]]+for[[:space:]]+([^[:space:]]+)[[:space:]]+from[[:space:]]+([^[:space:]]+) ]]; then
          local msk
          msk="$(journal_ts_to_msk "${BASH_REMATCH[1]}")"
          printf 'success\t%s\t%s\t%s\t%s\t%s\n' "$msk" "${BASH_REMATCH[3]}" "${BASH_REMATCH[4]}" "${BASH_REMATCH[2]}" "journalctl:sshd" >> "$AUTH_EVENTS"
        elif [[ "$line" =~ ^([^[:space:]]+)[[:space:]]+.*sshd.*Failed[[:space:]]+([^[:space:]]+)[[:space:]]+for[[:space:]]+(invalid[[:space:]]+user[[:space:]]+)?([^[:space:]]+)[[:space:]]+from[[:space:]]+([^[:space:]]+) ]]; then
          local msk
          msk="$(journal_ts_to_msk "${BASH_REMATCH[1]}")"
          printf 'failed\t%s\t%s\t%s\t%s\t%s\n' "$msk" "${BASH_REMATCH[4]}" "${BASH_REMATCH[5]}" "${BASH_REMATCH[2]}" "journalctl:sshd" >> "$AUTH_EVENTS"
        elif [[ "$line" =~ ^([^[:space:]]+)[[:space:]]+.*sudo:.*[[:space:]]${AUDIT_USER}[[:space:]]*:.*COMMAND=(.*)$ ]]; then
          local msk
          msk="$(journal_ts_to_msk "${BASH_REMATCH[1]}")"
          printf '%s\t%s\t%s\n' "$msk" "journalctl:sudo" "${BASH_REMATCH[2]}" >> "$SUDO_EVENTS"
        fi
      done
}

collect_auth_from_files() {
  shopt -s nullglob
  local files=(/var/log/auth.log /var/log/auth.log.1 /var/log/auth.log.*.gz /var/log/secure /var/log/secure.1 /var/log/secure.*.gz)
  shopt -u nullglob

  [ "${#files[@]}" -gt 0 ] || return 0

  for file in "${files[@]}"; do
    if [[ "$file" == *.gz ]]; then
      zgrep -hE 'sshd|sudo' "$file" 2>/dev/null || true
    else
      grep -hE 'sshd|sudo' "$file" 2>/dev/null || true
    fi
  done | while IFS= read -r line; do
    [ -n "$line" ] || continue
    local month day time_part msk
    month="$(awk '{print $1}' <<< "$line")"
    day="$(awk '{print $2}' <<< "$line")"
    time_part="$(awk '{print $3}' <<< "$line")"
    local event_epoch
    event_epoch="$(syslog_ts_to_epoch "$month" "$day" "$time_part")"
    if [ -n "$event_epoch" ] && [ "$event_epoch" -lt "$SINCE_EPOCH" ]; then
      continue
    fi
    msk="$(syslog_ts_to_msk "$month" "$day" "$time_part")"

    if [[ "$line" =~ sshd.*Accepted[[:space:]]+([^[:space:]]+)[[:space:]]+for[[:space:]]+([^[:space:]]+)[[:space:]]+from[[:space:]]+([^[:space:]]+) ]]; then
      printf 'success\t%s\t%s\t%s\t%s\t%s\n' "$msk" "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}" "${BASH_REMATCH[1]}" "auth.log:sshd" >> "$AUTH_EVENTS"
    elif [[ "$line" =~ sshd.*Failed[[:space:]]+([^[:space:]]+)[[:space:]]+for[[:space:]]+(invalid[[:space:]]+user[[:space:]]+)?([^[:space:]]+)[[:space:]]+from[[:space:]]+([^[:space:]]+) ]]; then
      printf 'failed\t%s\t%s\t%s\t%s\t%s\n' "$msk" "${BASH_REMATCH[3]}" "${BASH_REMATCH[4]}" "${BASH_REMATCH[1]}" "auth.log:sshd" >> "$AUTH_EVENTS"
    elif [[ "$line" =~ sudo:.*[[:space:]]${AUDIT_USER}[[:space:]]*:.*COMMAND=(.*)$ ]]; then
      printf '%s\t%s\t%s\n' "$msk" "auth.log:sudo" "${BASH_REMATCH[1]}" >> "$SUDO_EVENTS"
    fi
  done
}

dedupe_auth_events() {
  local file="$1"
  local tmp_file="${file}.dedupe"
  awk -F '\t' '!seen[$1 FS $2 FS $3 FS $4 FS $5]++' "$file" > "$tmp_file" 2>/dev/null || true
  mv "$tmp_file" "$file" 2>/dev/null || true
}

dedupe_sudo_events() {
  local file="$1"
  local tmp_file="${file}.dedupe"
  awk -F '\t' '!seen[$1 FS $3]++' "$file" > "$tmp_file" 2>/dev/null || true
  mv "$tmp_file" "$file" 2>/dev/null || true
}

print_auth_events() {
  local type="$1"
  local title="$2"
  print_subsection "$title"

  if ! awk -F '\t' -v type="$type" '$1 == type { found=1 } END { exit(found ? 0 : 1) }' "$AUTH_EVENTS"; then
    echo "Записей не найдено."
    return
  fi

  printf '%-25s %-20s %-45s %-16s %s\n' "Время МСК" "Аккаунт" "IP/хост" "Способ" "Источник"
  awk -F '\t' -v type="$type" '$1 == type { print $2 "\t" $3 "\t" $4 "\t" $5 "\t" $6 }' "$AUTH_EVENTS" \
    | tail -n "$LOGIN_LIMIT" \
    | awk -F '\t' '{ printf "%-25s %-20s %-45s %-16s %s\n", $1, $2, $3, $4, $5 }'
}

print_last_logins() {
  print_subsection "Успешные входы из wtmp/last"

  if ! has_cmd last; then
    echo "Команда last не найдена."
    return
  fi

  echo "Время выводится в часовом поясе: $TIMEZONE"
  if last --help 2>&1 | grep -q -- '--since'; then
    TZ="$TIMEZONE" last -F -i -w --since "$SINCE_DATE" 2>/dev/null | head -n "$LOGIN_LIMIT" || true
  else
    TZ="$TIMEZONE" last -F -i -w 2>/dev/null | head -n "$LOGIN_LIMIT" || true
  fi
}

print_user_login_summary() {
  print_subsection "Подключения пользователя ${AUDIT_USER}"

  if awk -F '\t' -v user="$AUDIT_USER" '$1 == "success" && $3 == user { found=1 } END { exit(found ? 0 : 1) }' "$AUTH_EVENTS"; then
    printf '%-25s %-45s %-16s %s\n' "Время МСК" "IP/хост" "Способ" "Источник"
    awk -F '\t' -v user="$AUDIT_USER" '$1 == "success" && $3 == user { print $2 "\t" $4 "\t" $5 "\t" $6 }' "$AUTH_EVENTS" \
      | tail -n "$LOGIN_LIMIT" \
      | awk -F '\t' '{ printf "%-25s %-45s %-16s %s\n", $1, $2, $3, $4 }'
  else
    echo "Успешных SSH-входов пользователя ${AUDIT_USER} не найдено."
  fi

  if has_cmd last; then
    echo
    echo "Сессии из last:"
    if last --help 2>&1 | grep -q -- '--since'; then
      TZ="$TIMEZONE" last -F -i -w "$AUDIT_USER" --since "$SINCE_DATE" 2>/dev/null | head -n "$LOGIN_LIMIT" || true
    else
      TZ="$TIMEZONE" last -F -i -w "$AUDIT_USER" 2>/dev/null | head -n "$LOGIN_LIMIT" || true
    fi
  fi
}

print_sudo_events() {
  print_subsection "Что ${AUDIT_USER} делал через sudo"

  if [ ! -s "$SUDO_EVENTS" ]; then
    echo "sudo-команд для ${AUDIT_USER} не найдено."
    return
  fi

  printf '%-25s %-18s %s\n' "Время МСК" "Источник" "Расшифровка"
  tail -n "$HISTORY_LIMIT" "$SUDO_EVENTS" | while IFS=$'\t' read -r ts source command_text; do
    [ -n "${command_text:-}" ] || continue
    printf '%-25s %-18s ' "$ts" "$source"
    explain_command "$command_text"
    printf '\n'
    printf '  Команда: %s\n' "$command_text"
  done
}

print_bash_history() {
  local file="$1"
  local source_name="$2"

  [ -r "$file" ] || return 0

  echo
  echo "Источник: $file"

  awk '
    /^#[0-9]{9,}$/ {
      ts=substr($0, 2)
      next
    }
    NF {
      if (ts != "") {
        print ts "\t" $0
        ts=""
      } else {
        print "NO_TIME\t" $0
      }
    }
  ' "$file" | tail -n "$HISTORY_LIMIT" | while IFS=$'\t' read -r ts command_text; do
    [ -n "${command_text:-}" ] || continue
    local shown_time
    if [ "$ts" = "NO_TIME" ]; then
      shown_time="время не записано"
    else
      shown_time="$(to_msk_from_epoch "$ts")"
    fi
    printf '%-25s %-12s ' "$shown_time" "$source_name"
    explain_command "$command_text"
    printf '\n'
    printf '  Команда: %s\n' "$command_text"
  done
}

print_zsh_history() {
  local file="$1"

  [ -r "$file" ] || return 0

  echo
  echo "Источник: $file"

  awk '
    /^: [0-9]+:[0-9]+;/ {
      line=$0
      sub(/^: /, "", line)
      split(line, parts, ";")
      split(parts[1], meta, ":")
      cmd=substr($0, index($0, ";") + 1)
      print meta[1] "\t" cmd
      next
    }
    NF {
      print "NO_TIME\t" $0
    }
  ' "$file" | tail -n "$HISTORY_LIMIT" | while IFS=$'\t' read -r ts command_text; do
    [ -n "${command_text:-}" ] || continue
    local shown_time
    if [ "$ts" = "NO_TIME" ]; then
      shown_time="время не записано"
    else
      shown_time="$(to_msk_from_epoch "$ts")"
    fi
    printf '%-25s %-12s ' "$shown_time" "zsh"
    explain_command "$command_text"
    printf '\n'
    printf '  Команда: %s\n' "$command_text"
  done
}

print_shell_history() {
  print_subsection "Что ${AUDIT_USER} делал по истории команд"

  local home_dir
  home_dir=""

  if has_cmd getent; then
    home_dir="$(getent passwd "$AUDIT_USER" 2>/dev/null | awk -F ':' '{print $6}' || true)"
  fi

  if [ -z "$home_dir" ] && [ -d "/home/$AUDIT_USER" ]; then
    home_dir="/home/$AUDIT_USER"
  fi

  if [ -z "$home_dir" ] && [ "$AUDIT_USER" = "$(id -un 2>/dev/null || true)" ] && [ -n "${HOME:-}" ]; then
    home_dir="$HOME"
  fi

  if [ -z "$home_dir" ]; then
    echo "Не нашел домашнюю папку пользователя ${AUDIT_USER}."
    return
  fi

  local found=0
  if [ -r "$home_dir/.bash_history" ]; then
    found=1
    print_bash_history "$home_dir/.bash_history" "bash"
  fi
  if [ -r "$home_dir/.zsh_history" ]; then
    found=1
    print_zsh_history "$home_dir/.zsh_history"
  fi
  if [ -r "$home_dir/.mysql_history" ]; then
    found=1
    echo
    echo "Источник: $home_dir/.mysql_history"
    tail -n "$HISTORY_LIMIT" "$home_dir/.mysql_history" | while IFS= read -r command_text; do
      [ -n "$command_text" ] || continue
      printf '%-25s %-12s %s\n' "время не записано" "mysql" "Работал в MySQL: $command_text"
    done
  fi

  if [ "$found" -eq 0 ]; then
    echo "Читаемой shell history для ${AUDIT_USER} не найдено."
  else
    echo
    echo "Если написано 'время не записано', значит в shell history не были включены временные метки."
  fi
}

print_process_accounting() {
  print_subsection "Process accounting / lastcomm"

  if ! has_cmd lastcomm; then
    echo "lastcomm не найден. Для будущего полного учета команд можно включить пакет acct/psacct."
    echo "Ubuntu/Debian: sudo apt install acct && sudo systemctl enable --now acct"
    return
  fi

  local output
  output="$(lastcomm "$AUDIT_USER" 2>/dev/null | head -n "$HISTORY_LIMIT" || true)"
  if [ -z "$output" ]; then
    echo "lastcomm установлен, но записей по ${AUDIT_USER} не найдено."
    return
  fi

  echo "$output" | while IFS= read -r line; do
    [ -n "$line" ] || continue
    local command_name
    command_name="$(awk '{print $1}' <<< "$line")"
    printf 'Запускал процесс: %s\n' "$command_name"
    printf '  Сырой журнал: %s\n' "$line"
  done
}

print_auditd_hint() {
  print_subsection "Auditd"

  if has_cmd auditctl && auditctl -s >/dev/null 2>&1; then
    echo "auditd установлен. Для максимально подробного будущего учета команд проверьте правила execve."
    echo "Пример проверки: sudo auditctl -l | grep execve"
    if has_cmd ausearch; then
      echo "Можно дополнительно смотреть: sudo ausearch -ua ${AUDIT_USER} -ts ${SINCE_DATE}"
    fi
  else
    echo "auditd не найден или недоступен. Старые действия без auditd восстановить полностью нельзя."
  fi
}

main() {
  print_section "Аудит подключений к серверу"
  echo "Отчет сформирован: $(msk_now)"
  echo "Период: с ${SINCE_DATE} 00:00:00"
  echo "Часовой пояс отчета: ${TIMEZONE}"
  echo "Подробный пользователь: ${AUDIT_USER}"

  if [ "$(id -u)" -ne 0 ]; then
    echo
    echo "Внимание: скрипт запущен не от root. Часть логов может быть недоступна."
    echo "Для полного отчета запустите: sudo ./audit-peredacha.sh"
  fi

  collect_auth_from_journal
  collect_auth_from_files
  dedupe_auth_events "$AUTH_EVENTS"
  dedupe_sudo_events "$SUDO_EVENTS"

  print_section "1. Кто подключался под аккаунтами"
  print_auth_events "success" "Успешные SSH-подключения"
  print_last_logins

  print_section "2. Неуспешные попытки входа"
  print_auth_events "failed" "Неуспешные SSH-попытки"

  print_section "3. Подробно по пользователю ${AUDIT_USER}"
  print_user_login_summary
  echo
  echo "Примечание: IP хранится в SSH/wtmp-сессиях, а команды обычно в sudo-логах и shell history без IP."
  echo "Если на сервере заранее не был включен auditd или process accounting, точную связку 'этот IP выполнил эту команду' Linux часто не хранит."
  print_sudo_events
  print_shell_history
  print_process_accounting
  print_auditd_hint

  print_section "Итог"
  echo "Отчет готов."
  echo "Для сохранения в файл можно запустить:"
  echo "sudo ./audit-peredacha.sh --user ${AUDIT_USER} --days ${DAYS} > server-audit-\$(date +%F_%H-%M).txt"
}

main "$@"
