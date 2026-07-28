#!/bin/bash
# Поднимает ИЗОЛИРОВАННЫЙ демо-инстанс для съёмки скриншотов/ролика.
#
# Отдельный data dir (tools/demo/.build/demo/data) — реальные данные
# (~/.config/hse-studio) не затрагиваются. Backend раздаёт собранный фронт сам
# (HSE_STUDIO__STATIC_DIR) — Playwright ходит на ОДИН порт, Vite не нужен.
#
# Требования: uv, Node+pnpm (для сборки фронта), Docker Desktop запущен
# (иначе в кадры попадёт красный баннер «Docker недоступен»).
#
# Оставьте процесс в этом терминале; в другом — `make shots` / `make reel`.
# Переопределяемо: PORT (default 17777), RESEED=1, FRONT_BUILD=1.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PORT="${PORT:-17777}"
DIST="$ROOT/services/web-app/dist"

echo "→ сею демо-стенд (изолированный data dir)…"
env -u PYTHONPATH python "$HERE/seed_demo.py"

if [ ! -f "$DIST/index.html" ] || [ "${FRONT_BUILD:-0}" = "1" ]; then
  echo "→ собираю фронт (pnpm build)…"
  (cd "$ROOT/services/web-app" && pnpm build)
fi

echo "→ backend на http://127.0.0.1:${PORT} (демо-данные, фид обновлений off)…  Ctrl+C чтобы остановить."
cd "$ROOT/services/api"
exec env -u PYTHONPATH \
  HSE_STUDIO__DATA_DIR="$HERE/.build/demo/data" \
  HSE_STUDIO__STATIC_DIR="$DIST" \
  HSE_STUDIO__SERVER__HOST=127.0.0.1 \
  HSE_STUDIO__SERVER__PORT="$PORT" \
  HSE_STUDIO__UPDATE_FEED_URL=off \
  HSE_STUDIO__COMPILE__PREFETCH_IMAGE=false \
  HSE_STUDIO__AGENT__DEBUG_TRACE=false \
  HSE_STUDIO__LOGGING__LEVEL=WARNING \
  uv run --extra api python -m hse_doc_studio.api.entrypoint
