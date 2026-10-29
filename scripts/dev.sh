#!/usr/bin/env bash
# Локальный запуск для разработки одной командой вместо пяти окон терминала.
#
#   scripts/dev.sh up      – проверить окружение и запустить всё в фоне
#   scripts/dev.sh status  – какие сервисы живы
#   scripts/dev.sh logs X  – показать журнал сервиса X (auth, livekit, dev-api, client), Ctrl-C – выйти
#   scripts/dev.sh down    – остановить сервисы (PostgreSQL и Redis в Docker остаются)
#   scripts/dev.sh down all – остановить и PostgreSQL с Redis
#
# Запускает: PostgreSQL и Redis (Docker), auth-service :8001, livekit-server :7880, dev-api :8002,
# клиент (Vite, VITE_API_MODE=http) :5173. Журналы – .dev/logs/, PID – .dev/pids/ (в git не попадают).
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="$ROOT/.dev"
LOGS="$STATE/logs"
PIDS="$STATE/pids"
COMPOSE=(docker compose -f "$ROOT/deploy/docker-compose.dev.yml")
SERVICES=(auth livekit dev-api client)

# bash 3.2 из macOS не знает ассоциативных массивов
port_of() {
  case "$1" in
    auth) echo 8001 ;;
    livekit) echo 7880 ;;
    dev-api) echo 8002 ;;
    client) echo 5173 ;;
  esac
}

red() { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
step() { printf '\033[36m==> %s\033[0m\n' "$*"; }

listening() { lsof -iTCP:"$1" -sTCP:LISTEN -t >/dev/null 2>&1; }

pid_alive() {
  local file="$PIDS/$1.pid"
  [[ -f "$file" ]] && kill -0 "$(cat "$file")" 2>/dev/null
}

# Ждем, пока порт начнет слушаться; если процесс умер раньше – показываем хвост журнала.
wait_port() {
  local name=$1 port=$2 tries=${3:-60}
  for ((i = 0; i < tries; i++)); do
    if listening "$port"; then return 0; fi
    if ! pid_alive "$name"; then
      red "$name завершился, не дождавшись порта $port. Последние строки журнала ($LOGS/$name.log):"
      tail -n 15 "$LOGS/$name.log" | sed 's/^/    /'
      return 1
    fi
    sleep 1
  done
  red "$name не открыл порт $port за ${tries} с. Журнал: $LOGS/$name.log"
  return 1
}

# Запуск в фоне (DETACH задан ниже, до первого вызова)
start() {
  local name=$1 dir=$2
  shift 2
  local port
  port="$(port_of "$name")"
  if listening "$port"; then
    green "$name уже запущен (порт $port), пропускаю"
    return 0
  fi
  step "запуск $name"
  (
    cd "$dir" || exit 1
    exec "${DETACH[@]}" "$@" >"$LOGS/$name.log" 2>&1 </dev/null
  ) &
  echo $! >"$PIDS/$name.pid"
  wait_port "$name" "$port"
}

node_version_ok() {
  local v major minor
  v="$(node -v 2>/dev/null)" || return 1
  v="${v#v}"
  major="${v%%.*}"
  minor="${v#*.}"
  minor="${minor%%.*}"
  ((major > 22 || (major == 22 && minor >= 18)))
}

preflight() {
  step "проверка окружения"
  local ok=1
  for tool in docker uv pnpm lsof livekit-server; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      red "не найдена команда $tool (macOS: brew install ${tool/livekit-server/livekit})"
      ok=0
    fi
  done
  if command -v node >/dev/null 2>&1; then
    if ! node -e 'process.exit(0)' 2>/dev/null; then
      red "node не запускается ($(command -v node)). На macOS это бывает после brew upgrade:"
      red "  brew reinstall node@22 && brew link --overwrite --force node@22"
      ok=0
    elif ! node_version_ok; then
      red "нужен Node 22.18 или новее, сейчас $(node -v) ($(command -v node))"
      red "  brew install node@22 && export PATH=\"/opt/homebrew/opt/node@22/bin:\$PATH\""
      ok=0
    fi
  else
    red "не найден node"
    ok=0
  fi
  if command -v docker >/dev/null 2>&1 && ! docker info >/dev/null 2>&1; then
    red "Docker не запущен: открой Docker Desktop и дождись статуса running"
    ok=0
  fi
  ((ok)) || exit 1
  green "окружение в порядке (node $(node -v))"
}

# Отдельная группа процессов: `down` останавливает сервис вместе с дочерними процессами.
# setsid есть в Linux, но не в macOS: там тот же вызов делает perl (он есть в системе).
if command -v setsid >/dev/null 2>&1; then
  DETACH=(setsid)
else
  DETACH=(perl -e 'use POSIX qw(setsid); setsid(); exec @ARGV or die "exec: $!"' --)
fi

prepare_backend() {
  local env="$ROOT/backend/services/auth_service/.env"
  step "база данных и миграции"
  "${COMPOSE[@]}" up -d --wait postgres redis || { red "не удалось запустить PostgreSQL и Redis"; exit 1; }
  if [[ ! -f "$env" ]]; then
    cp "$env.example" "$env"
    green "создан $env"
  fi
  # Kafka локально не запускаем: без неё auth-service лишь копит события, а в журнал каждые 5 с
  # пишется ошибка подключения. Отключаем строку, пока на 9092 никто не слушает.
  if ! listening 9092 && grep -q '^KAFKA_BOOTSTRAP_SERVERS=' "$env"; then
    sed -i.bak 's/^KAFKA_BOOTSTRAP_SERVERS=/# KAFKA_BOOTSTRAP_SERVERS=/' "$env" && rm -f "$env.bak"
    green "Kafka не запущена: в $env строка KAFKA_BOOTSTRAP_SERVERS закомментирована"
  fi
  (cd "$ROOT/backend" && make sync migrate-auth jwt-key >"$LOGS/prepare.log" 2>&1) \
    || { red "make sync migrate-auth jwt-key не прошел:"; tail -n 15 "$LOGS/prepare.log" | sed 's/^/    /'; exit 1; }
  (cd "$ROOT/frontend" && pnpm install --frozen-lockfile >>"$LOGS/prepare.log" 2>&1) \
    || { red "pnpm install не прошел:"; tail -n 15 "$LOGS/prepare.log" | sed 's/^/    /'; exit 1; }
}

cmd_up() {
  mkdir -p "$LOGS" "$PIDS"
  preflight
  prepare_backend

  # meeting-service: временный dev-api (frontend/dev-api/README.md), настоящий пока не подключен к клиенту.
  start auth "$ROOT/backend" \
    uv run --env-file services/auth_service/.env uvicorn auth_service.main:create_application \
    --factory --host 127.0.0.1 --port 8001 || exit 1
  start livekit "$ROOT" livekit-server --dev --bind 127.0.0.1 || exit 1
  start dev-api "$ROOT/frontend" node dev-api/server.ts || exit 1
  start client "$ROOT/frontend" env VITE_API_MODE=http pnpm dev || exit 1

  echo
  green "Все сервисы запущены."
  echo "  Клиент:    http://localhost:5173   (открывай именно localhost, не 127.0.0.1)"
  echo "  Журналы:   scripts/dev.sh logs auth|livekit|dev-api|client"
  echo "  Остановка: scripts/dev.sh down"
  echo
  echo "Встречи хранятся в памяти dev-api: после его перезапуска создавай встречу заново."
}

cmd_status() {
  local bad=0
  for name in "${SERVICES[@]}"; do
    if listening "$(port_of "$name")"; then
      printf '  %-9s порт %-5s \033[32mработает\033[0m\n' "$name" "$(port_of "$name")"
    else
      printf '  %-9s порт %-5s \033[31mне работает\033[0m  (журнал: .dev/logs/%s.log)\n' "$name" "$(port_of "$name")" "$name"
      bad=1
    fi
  done
  if "${COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -q postgres; then
    printf '  %-9s порт %-5s \033[32mработает\033[0m\n' postgres 5432
  else
    printf '  %-9s порт %-5s \033[31mне работает\033[0m  (scripts/dev.sh up)\n' postgres 5432
    bad=1
  fi
  return $bad
}

cmd_logs() {
  local name=${1:-}
  [[ -n "$name" && -f "$LOGS/$name.log" ]] || { red "usage: scripts/dev.sh logs auth|livekit|dev-api|client"; exit 1; }
  tail -n 50 -f "$LOGS/$name.log"
}

cmd_down() {
  for name in "${SERVICES[@]}"; do
    if pid_alive "$name"; then
      local pid
      pid="$(cat "$PIDS/$name.pid")"
      # группа процессов, затем сам процесс
      kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
      green "остановлен $name"
    fi
    rm -f "$PIDS/$name.pid"
  done
  if [[ "${1:-}" == "all" ]]; then
    "${COMPOSE[@]}" stop postgres redis >/dev/null && green "остановлены PostgreSQL и Redis (данные сохранены)"
  fi
}

case "${1:-}" in
  up) cmd_up ;;
  status) cmd_status ;;
  logs) shift; cmd_logs "$@" ;;
  down) shift; cmd_down "$@" ;;
  *) sed -n '2,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
