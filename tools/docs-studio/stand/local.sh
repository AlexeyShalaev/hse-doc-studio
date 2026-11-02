#!/usr/bin/env bash
# Локальная Студия для съёмки справки: изолированный каталог данных, бэкенд раздаёт собранный
# интерфейс и справку сам (один порт, без Vite), фид обновлений выключен.
#
#   stand/local.sh start   # собрать недостающее, поднять в фоне на :${PORT}, дождаться /health
#   stand/local.sh stop
#   stand/local.sh reset   # стереть данные и проекты стенда (следующий start засеет заново)
#
# Реальные данные (~/.config/hse-studio) не затрагиваются. Папки проектов лежат в
# ~/Documents/hse-studio-docs: путь виден в кадрах, служебный .build там выглядел бы как леса.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PORT="${DOCS_LOCAL_PORT:-17790}"
BUILD="$HERE/.build/local"
DATA="$BUILD/data"
PIDFILE="$BUILD/api.pid"
LOG="$BUILD/api.log"
export DOCS_PROJECTS_HOME="${DOCS_PROJECTS_HOME:-$HOME/Documents/hse-studio-docs}"
MARKER="$DOCS_PROJECTS_HOME/.hse-studio-docs-stand"

stop() {
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    kill "$(cat "$PIDFILE")" && echo "локальный стенд остановлен"
  fi
  rm -f "$PIDFILE"
}

case "${1:-start}" in
  stop) stop; exit 0 ;;
  reset)
    stop
    rm -rf "$BUILD"
    if [ -d "$DOCS_PROJECTS_HOME" ]; then
      [ -f "$MARKER" ] || { echo "$DOCS_PROJECTS_HOME создан не стендом, не трогаю" >&2; exit 1; }
      rm -rf "$DOCS_PROJECTS_HOME"
    fi
    echo "стенд сброшен"; exit 0 ;;
  start) ;;
  *) echo "usage: $0 start|stop|reset" >&2; exit 2 ;;
esac

stop
mkdir -p "$DATA" "$DOCS_PROJECTS_HOME"
touch "$MARKER"

if [ ! -f "$ROOT/services/web-app/dist/index.html" ] || [ "${FRONT_BUILD:-0}" = "1" ]; then
  echo "→ собираю интерфейс"; (cd "$ROOT/services/web-app" && pnpm install --frozen-lockfile >/dev/null && pnpm build >/dev/null)
fi
if [ ! -d "$ROOT/services/user-docs/dist/user" ] || [ "${HELP_BUILD:-0}" = "1" ]; then
  echo "→ собираю справку"; (cd "$ROOT/services/user-docs" && pnpm install --frozen-lockfile >/dev/null && pnpm build >/dev/null)
fi

echo "→ бэкенд на http://127.0.0.1:$PORT (журнал $LOG)"
cd "$ROOT/services/api"
env -u PYTHONPATH \
  HSE_STUDIO__MODE=local \
  HSE_STUDIO__DATA_DIR="$DATA" \
  HSE_STUDIO__STATIC_DIR="$ROOT/services/web-app/dist" \
  HSE_STUDIO__HELP_DIR="$ROOT/services/user-docs/dist" \
  HSE_STUDIO__SERVER__HOST=127.0.0.1 \
  HSE_STUDIO__SERVER__PORT="$PORT" \
  HSE_STUDIO__UPDATE_FEED_URL=off \
  HSE_STUDIO__COMPILE__PREFETCH_IMAGE=false \
  HSE_STUDIO__LOGGING__LEVEL=WARNING \
  nohup uv run --extra api python -m hse_doc_studio.api.entrypoint >"$LOG" 2>&1 &
echo $! >"$PIDFILE"

for _ in $(seq 1 90); do
  curl -sf "http://127.0.0.1:$PORT/health" >/dev/null && { echo "локальный стенд готов: http://127.0.0.1:$PORT"; exit 0; }
  sleep 1
done
echo "бэкенд не поднялся, хвост журнала:" >&2; tail -40 "$LOG" >&2; exit 1
