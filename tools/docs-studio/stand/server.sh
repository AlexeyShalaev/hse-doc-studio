#!/usr/bin/env bash
# Серверная Студия для съёмки справки: compose стенда server-lite (образ приложения в режиме server
# и Postgres, scripts/dev/server-lite) под своим именем проекта и портом, чтобы не задеть ни dev-стенд,
# ни e2e. Образ собирается из текущих исходников: в кадре ровно то, что уедет в релиз.
#
#   stand/server.sh up     # поднять и засеять демо-данными (идемпотентно)
#   stand/server.sh down   # остановить, данные остаются
#   stand/server.sh reset  # остановить и стереть данные стенда
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
LITE="$ROOT/scripts/dev/server-lite"
BUILD="$ROOT/tools/docs-studio/.build"
ENV_FILE="$BUILD/server.env"
export SERVER_LITE_PORT="${DOCS_SERVER_PORT:-8110}"
mkdir -p "$BUILD"
if [ ! -f "$ENV_FILE" ]; then
  umask 077
  {
    echo "SERVER_LITE_PG_PASSWORD=$(openssl rand -hex 16)"
    echo "SERVER_LITE_SECRETS_KEY=$(openssl rand 32 | openssl base64 -A | tr '+/' '-_')"
    echo "SERVER_LITE_ADMIN_PASSWORD=admin-$(openssl rand -hex 6)"
    echo "SERVER_LITE_SEED_PASSWORD=demo-$(openssl rand -hex 6)"
    echo "SERVER_LITE_PORT=$SERVER_LITE_PORT"
  } >"$ENV_FILE"
fi
compose() { docker compose -p hse-doc-studio-docs -f "$LITE/compose.yml" --env-file "$ENV_FILE" "$@"; }
case "${1:-up}" in
  up)
    compose up --build -d --wait
    compose --profile seed run --rm --build seed
    echo "серверный стенд готов: http://localhost:$SERVER_LITE_PORT" ;;
  down) compose --profile seed down ;;
  reset) compose --profile seed down --volumes --remove-orphans; rm -f "$ENV_FILE" ;;
  *) echo "usage: $0 up|down|reset" >&2; exit 2 ;;
esac
