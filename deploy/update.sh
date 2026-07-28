#!/bin/sh
# Обновление hse-doc-studio на macOS и Linux — ТЕМ ЖЕ механизмом, что и кнопка
# «Обновить» в приложении: соседний контейнер-апдейтер пересоздаёт студию с
# сохранением всех её флагов (порты, бинды, переменные), ждёт здоровья и САМ
# откатывается на прежнюю версию, если новая не поднялась. Папка данных не
# трогается. Скрипт нужен, когда интерфейс недоступен или просто удобнее из
# терминала; переустановка с нуля при этом не требуется.
#
# Контракт апдейтера (стабильный):
#   python -m hse_doc_studio.infra.update.updater <контейнер> <новый образ>
# Модуль лежит в самом образе приложения, поэтому логика здесь не дублируется.
#
# POSIX sh: скрипт запускают через `curl ... | sh`, /bin/sh на Debian — dash.
set -eu

IMAGE="${HSE_STUDIO_IMAGE:-ghcr.io/alexeyshalaev/hse-doc-studio:${TAG:-latest}}"
NAME="${HSE_STUDIO_NAME:-hse-doc-studio}"
UPDATER_NAME="hse-studio-updater"
DOCKER_SOCK="${DOCKER_SOCK:-/var/run/docker.sock}"

# Язык сообщений: HSE_STUDIO_LANG=ru — русский, иначе английский.
case "${HSE_STUDIO_LANG:-en}" in
    ru | RU | ru_* | ru-*) LANG_RU=1 ;;
    *) LANG_RU=0 ;;
esac

OS="$(uname -s)"

say() { printf '%s\n' "$*"; }
loc() { if [ "$LANG_RU" = 1 ]; then printf '%s' "$1"; else printf '%s' "$2"; fi; }
die() {
    printf '%s: %s\n' "$(loc 'ошибка' 'error')" "$*" >&2
    exit 1
}

command -v docker >/dev/null 2>&1 || die "$(loc 'не найден docker.' 'docker not found.')"
docker info >/dev/null 2>&1 || die "$(loc 'демон докера не отвечает — запустите его и повторите.' \
    'the docker daemon is not responding — start it and retry.')"

docker inspect "$NAME" >/dev/null 2>&1 || die "$(loc "контейнер $NAME не найден. Сначала установка:
    curl -fsSL https://raw.githubusercontent.com/AlexeyShalaev/hse-doc-studio/master/deploy/install.sh | HSE_STUDIO_LANG=ru sh" \
    "container $NAME not found. Install first:
    curl -fsSL https://raw.githubusercontent.com/AlexeyShalaev/hse-doc-studio/master/deploy/install.sh | sh")"

CURRENT="$(docker inspect -f '{{.Config.Image}}' "$NAME" 2>/dev/null || true)"
say "$(loc "текущий образ: $CURRENT" "current image: $CURRENT")"
say "$(loc "скачиваю $IMAGE" "pulling $IMAGE")"
# Неудачный pull не смертелен: апдейтер попробует скачать сам (у него свой таймаут).
docker pull "$IMAGE" >/dev/null 2>&1 || say "$(loc 'скачать заранее не вышло — апдейтер попробует сам.' \
    'pre-pull failed — the updater will retry on its own.')"

# gid группы-владельца сокета: без членства в ней апдейтер, работающий от
# непривилегированного app, не смог бы даже сделать docker inspect.
if [ "$OS" = "Linux" ]; then
    SOCK_GID="$(stat -c '%g' "$DOCKER_SOCK" 2>/dev/null || echo 0)"
else
    SOCK_GID=0
fi

# Остатки прошлого запуска (его логи больше не нужны).
docker rm -f "$UPDATER_NAME" >/dev/null 2>&1 || true

say "$(loc 'запускаю апдейтер — пересоздание с сохранением настроек, при неудаче автооткат.' \
    'starting the updater — recreation with settings preserved, automatic rollback on failure.')"
docker run -d \
    --name "$UPDATER_NAME" \
    --label com.hse-studio.managed=true \
    -v "$DOCKER_SOCK:/var/run/docker.sock" \
    --group-add "$SOCK_GID" \
    "$IMAGE" \
    python -m hse_doc_studio.infra.update.updater "$NAME" "$IMAGE" >/dev/null

# Логи апдейтера идут в реальном времени; поток заканчивается вместе с ним.
docker logs -f "$UPDATER_NAME" 2>&1 || true
RC="$(docker wait "$UPDATER_NAME" 2>/dev/null || echo 1)"

FINAL="$(docker inspect -f '{{.Config.Image}}' "$NAME" 2>/dev/null || true)"
PORT="$(docker port "$NAME" 8000/tcp 2>/dev/null | head -n 1 | sed 's/.*://')"
if [ "$RC" = 0 ] && [ -n "$FINAL" ]; then
    say ""
    say "$(loc "готово: $NAME теперь на $FINAL" "done: $NAME is now on $FINAL")"
    [ -n "$PORT" ] && say "  http://localhost:$PORT"
else
    die "$(loc "обновление не удалось (апдейтер завершился с кодом $RC) — приложение осталось/откатилось на прежнюю версию.
  Подробности: docker logs $UPDATER_NAME" \
        "update failed (updater exited with code $RC) — the app stayed on / rolled back to the previous version.
  Details: docker logs $UPDATER_NAME")"
fi
