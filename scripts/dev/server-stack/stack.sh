#!/usr/bin/env bash
# Полный стенд server-режима для приёмочного смоука: deploy/server + compose.smoke.yml, секреты в .env рядом.
#   stack.sh build     собрать образ с extra server под тегом TAG (по умолчанию ci)
#   stack.sh up        поднять стенд из образа ghcr.io/alexeyshalaev/hse-doc-studio:$TAG
#   stack.sh env       напечатать переменные для e2e (E2E_BASE_URL, E2E_COMPOSE, ...)
#   stack.sh logs      журнал сервиса: stack.sh logs api
#   stack.sh down      остановить и стереть данные
#   stack.sh personal-up TOKEN  поднять личный раннер Анны (токен hsrt_ из «Мои раннеры») и поддельный OpenAI
#   stack.sh personal-stop      мягко остановить личный раннер (SIGTERM: раннер успевает сказать /offline)
#   stack.sh personal-kill      убить личный раннер без ухода (SIGKILL: сервер узнаёт о пропаже по тишине)
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../../.." && pwd)"
env_file="$here/.env"
project="hse-doc-studio-stack"
port="${STACK_PORT:-17251}"
compose=(docker compose -p "$project" --env-file "$env_file" -f "$root/deploy/server/docker-compose.yml" -f "$root/deploy/server/compose.smoke.yml" -f "$root/deploy/server/compose.personal.yml")

ensure_env() {
  [ -f "$env_file" ] && return
  umask 077
  runner_dir="${STACK_RUNNER_DIR:-$here/runner-data}"
  mkdir -p "$runner_dir"
  chmod 777 "$runner_dir"
  {
    echo "TAG=${TAG:-ci}"
    echo "PORT=$port"
    echo "PUBLIC_URL=http://localhost:$port"
    echo "POSTGRES_PASSWORD=$(openssl rand -hex 16)"
    echo "SECRETS_KEY=$(openssl rand 32 | openssl base64 -A | tr '+/' '-_')"
    echo "S3_ACCESS_KEY=stack$(openssl rand -hex 4)"
    echo "S3_SECRET_KEY=$(openssl rand -hex 16)"
    echo "S3_BUCKET=studio"
    echo "RUNNER_BOOTSTRAP_TOKEN=$(openssl rand -hex 32)"
    echo "RUNNER_DATA_DIR=$runner_dir"
    echo "RUNNER_CONCURRENCY=2"
    echo "DOCKER_GID=${DOCKER_GID:-$(stat -c '%g' /var/run/docker.sock 2>/dev/null || echo 0)}"
    echo "ONLYOFFICE_JWT_SECRET=$(openssl rand -hex 16)"
    echo "E2E_PASSWORD=stack-$(openssl rand -hex 6)"
  } > "$env_file"
}

wait_ready() {
  for _ in $(seq 1 90); do
    curl -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1 && return 0
    sleep 2
  done
  echo "api не поднялся за 3 минуты" >&2
  "${compose[@]}" logs --no-color --tail 200 api >&2 || true
  return 1
}

case "${1:-}" in
  build)
    docker build -f "$root/deploy/all-in-one/Dockerfile" --target production --build-arg BACKEND_EXTRAS="--extra server" \
      -t "ghcr.io/alexeyshalaev/hse-doc-studio:${TAG:-ci}" "$root"
    ;;
  up)
    ensure_env
    "${compose[@]}" up -d
    wait_ready
    ;;
  env)
    ensure_env
    # Токен установки печатается в журнале api при старте и живёт до создания админа.
    echo "export E2E_BASE_URL=http://localhost:$port"
    echo "export E2E_COMPOSE='${compose[*]}'"
    echo "export E2E_PASSWORD=$(grep '^E2E_PASSWORD=' "$env_file" | cut -d= -f2)"
    ;;
  logs)
    "${compose[@]}" logs --no-color "${2:-api}"
    ;;
  personal-up)
    ensure_env
    token="${2:?usage: $0 personal-up TOKEN}"
    personal_dir="${STACK_PERSONAL_RUNNER_DIR:-$here/runner-personal-data}"
    mkdir -p "$personal_dir"
    chmod 777 "$personal_dir"
    PERSONAL_RUNNER_TOKEN="$token" PERSONAL_RUNNER_DATA_DIR="$personal_dir" \
      "${compose[@]}" --profile personal up -d fake-openai runner-personal
    ;;
  personal-stop)
    "${compose[@]}" --profile personal stop -t 30 runner-personal
    ;;
  personal-kill)
    "${compose[@]}" --profile personal kill -s SIGKILL runner-personal
    ;;
  down)
    [ -f "$env_file" ] || exit 0
    "${compose[@]}" --profile personal down --volumes --remove-orphans
    rm -rf "$env_file" "$here/runner-data" "$here/runner-personal-data"
    ;;
  *)
    echo "usage: $0 build|up|env|logs [service]|down|personal-up TOKEN|personal-stop|personal-kill" >&2
    exit 2
    ;;
esac
