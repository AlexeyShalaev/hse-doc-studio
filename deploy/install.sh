#!/bin/sh
# Запуск hse-doc-studio на macOS и Linux.
#
# Скрипт намеренно ничего не спрашивает. Раньше установка требовала выбрать
# каталог данных, вычислить gid docker-сокета и собрать .env — три места, где
# можно ошибиться молча. Теперь всё это умеет сам продукт: контейнер поднимается
# БЕЗ единого бинда, показывает мастер первоначальной настройки, спрашивает одну
# папку и пересоздаёт себя с нужными -v и переменными. Здесь остаётся ровно три
# шага: жив ли докер — запустить — открыть браузер.
#
# POSIX sh (не bash): скрипт часто запускают через `curl ... | sh`, а /bin/sh на
# Debian и Ubuntu — это dash, который не знает ни массивов, ни [[ ]].
set -eu

# Образ и тег переопределяются переменными окружения — тем же способом, что и в
# docker-compose.yml, чтобы обе установки настраивались одинаково.
IMAGE="${HSE_STUDIO_IMAGE:-ghcr.io/alexeyshalaev/hse-doc-studio:${TAG:-latest}}"
NAME="${HSE_STUDIO_NAME:-hse-doc-studio}"
# Colima и Rancher Desktop держат сокет в домашнем каталоге, а не в /var/run;
# без этой переменной их пользователям пришлось бы править скрипт руками.
DOCKER_SOCK="${DOCKER_SOCK:-/var/run/docker.sock}"
FIRST_PORT="${PORT:-17240}"
# Сколько соседних портов пробовать, если наш занят.
PORT_ATTEMPTS=10
# Ждём столько секунд первого ответа /health: первый старт дольше обычного —
# приложение раскладывает пак шаблонов и проверяет докер.
HEALTH_TIMEOUT=120
HEALTH_POLL=2

# Язык сообщений: HSE_STUDIO_LANG=ru — русский, всё остальное (и умолчание) —
# английский. Документация подставляет флаг сама по языку открытой страницы.
case "${HSE_STUDIO_LANG:-en}" in
    ru | RU | ru_* | ru-*) LANG_RU=1 ;;
    *) LANG_RU=0 ;;
esac

OS="$(uname -s)"
HTTP_TOOL=""

say() { printf '%s\n' "$*"; }
# loc "по-русски" "in English" — выбор строки по HSE_STUDIO_LANG.
loc() { if [ "$LANG_RU" = 1 ]; then printf '%s' "$1"; else printf '%s' "$2"; fi; }
die() {
    printf '%s: %s\n' "$(loc 'ошибка' 'error')" "$*" >&2
    exit 1
}

# ── 1. Докер ────────────────────────────────────────────────────────────────

check_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        if [ "$OS" = "Darwin" ]; then
            die "$(loc 'не найден docker. Поставьте Docker Desktop: https://www.docker.com/products/docker-desktop/' \
                'docker not found. Install Docker Desktop: https://www.docker.com/products/docker-desktop/')"
        fi
        die "$(loc 'не найден docker. Поставьте Docker Engine: https://docs.docker.com/engine/install/' \
            'docker not found. Install Docker Engine: https://docs.docker.com/engine/install/')"
    fi

    # `docker info` вместо `docker version`: второй отвечает и без демона —
    # клиент печатает свою версию и молча выходит с нулём.
    if _err="$(docker info 2>&1 >/dev/null)"; then
        return 0
    fi
    case "$_err" in
        *"permission denied"*)
            die "$(loc 'нет доступа к докеру от текущего пользователя.
  Добавьте себя в группу docker и перелогиньтесь:
    sudo usermod -aG docker $USER' \
                "no access to docker for the current user.
  Add yourself to the docker group and re-login:
    sudo usermod -aG docker \$USER")"
            ;;
    esac
    if [ "$OS" = "Darwin" ]; then
        die "$(loc 'демон докера не отвечает — запустите Docker Desktop и повторите.' \
            'the docker daemon is not responding — start Docker Desktop and retry.')
$_err"
    fi
    die "$(loc 'демон докера не отвечает — запустите его (sudo systemctl start docker) и повторите.' \
        'the docker daemon is not responding — start it (sudo systemctl start docker) and retry.')
$_err"
}

# Группа-владелец сокета. Процесс в контейнере работает под непривилегированным
# `app`, а сокет приезжает с правами владельца с ХОСТА: без членства в его группе
# любое обращение к докеру падает с "permission denied" — то есть не собирается
# ни один документ. На Docker Desktop (macOS) сокет отдаётся как root:root,
# поэтому там достаточно группы 0; на Linux он обычно root:docker.
socket_group() {
    if [ "$OS" = "Linux" ]; then
        stat -c '%g' "$DOCKER_SOCK" 2>/dev/null || echo 0
        return 0
    fi
    echo 0
}

# ── 2. Запуск ───────────────────────────────────────────────────────────────

start_container() {
    # $GROUP_ARGS раскрывается БЕЗ кавычек намеренно: в POSIX sh нет массивов, а
    # значение — заведомо два слова из флага и числа.
    # shellcheck disable=SC2086
    docker run -d \
        --name "$NAME" \
        --restart unless-stopped \
        -p "$1:8000" \
        -v "$DOCKER_SOCK:/var/run/docker.sock" \
        --add-host=host.docker.internal:host-gateway \
        -e HSE_STUDIO__SERVER__PORT=8000 \
        $GROUP_ARGS \
        "$IMAGE" 2>&1 >/dev/null
}

# Порт хоста, на котором контейнер реально опубликован. Спрашиваем докер, а не
# помним своё: контейнер мог остаться от прошлого запуска с другим портом.
published_port() {
    docker port "$NAME" 8000/tcp 2>/dev/null | head -n 1 | sed 's/.*://'
}

# ── 3. Здоровье и браузер ───────────────────────────────────────────────────

pick_http_tool() {
    if command -v curl >/dev/null 2>&1; then
        HTTP_TOOL="curl"
    elif command -v wget >/dev/null 2>&1; then
        HTTP_TOOL="wget"
    fi
}

http_ok() {
    if [ "$HTTP_TOOL" = "curl" ]; then
        curl -fsS -o /dev/null --max-time 3 "$1" 2>/dev/null
        return $?
    fi
    wget -q -O /dev/null -T 3 "$1" 2>/dev/null
}

wait_healthy() {
    _deadline=$(($(date +%s) + HEALTH_TIMEOUT))
    while [ "$(date +%s)" -lt "$_deadline" ]; do
        if http_ok "http://127.0.0.1:$1/health"; then
            return 0
        fi
        # Упавший контейнер здоровым уже не станет — ждать таймаут незачем.
        if [ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" != "true" ]; then
            return 1
        fi
        sleep "$HEALTH_POLL"
    done
    return 1
}

open_browser() {
    if [ "$OS" = "Darwin" ]; then
        if command -v open >/dev/null 2>&1; then
            open "$1" >/dev/null 2>&1 || true
            return 0
        fi
        return 1
    fi
    for _opener in xdg-open wslview gio; do
        if command -v "$_opener" >/dev/null 2>&1; then
            # gio ждёт подкоманду; остальные — сразу адрес.
            if [ "$_opener" = "gio" ]; then
                gio open "$1" >/dev/null 2>&1 || true
            else
                "$_opener" "$1" >/dev/null 2>&1 || true
            fi
            return 0
        fi
    done
    return 1
}

finish() {
    _url="http://localhost:$1"
    if [ -z "$HTTP_TOOL" ]; then
        say "$(loc 'ни curl, ни wget не найдены — проверить готовность нечем, открываю адрес как есть.' \
            'neither curl nor wget found — cannot check readiness, opening the address as is.')"
    elif wait_healthy "$1"; then
        say "$(loc 'приложение отвечает.' 'the app is responding.')"
    else
        say "$(loc "приложение не ответило за ${HEALTH_TIMEOUT}с. Посмотрите логи: docker logs $NAME" \
            "the app did not respond within ${HEALTH_TIMEOUT}s. Check the logs: docker logs $NAME")"
    fi
    open_browser "$_url" || say "$(loc 'браузер открыть нечем — откройте адрес вручную.' \
        'no way to open a browser — open the address manually.')"
    say ""
    say "  $_url"
    say ""
    say "$(loc 'При первом запуске приложение спросит папку для ваших файлов и перезапустится
само — вкладку можно не закрывать, она дождётся.' \
        'On first launch the app will ask for a folder for your files and restart
itself — keep the tab open, it will wait.')"
    say ""
    say "$(loc "  логи:       docker logs -f $NAME
  остановить: docker stop $NAME
  удалить:    docker rm -f $NAME" \
        "  logs:    docker logs -f $NAME
  stop:    docker stop $NAME
  remove:  docker rm -f $NAME")"
}

# ── Сценарий ────────────────────────────────────────────────────────────────

check_docker
pick_http_tool

if [ ! -e "$DOCKER_SOCK" ]; then
    # Смонтировать несуществующий путь докер не откажется — он молча создаст
    # каталог, и приложение получит вместо сокета пустую папку.
    die "$(loc "не найден docker-сокет $DOCKER_SOCK.
  Docker Desktop: включите «Allow the default Docker socket to be used» в настройках.
  Colima/Rancher: укажите свой путь, например
    DOCKER_SOCK=\$HOME/.colima/default/docker.sock sh install.sh" \
        "docker socket $DOCKER_SOCK not found.
  Docker Desktop: enable \"Allow the default Docker socket to be used\" in settings.
  Colima/Rancher: point to your own path, e.g.
    DOCKER_SOCK=\$HOME/.colima/default/docker.sock sh install.sh")"
fi

# Уже установлено — не пересоздаём молча: у существующего контейнера может быть
# выбранная пользователем папка данных, и потерять её из-за повторного запуска
# скрипта было бы худшим, что этот скрипт умеет.
if docker inspect "$NAME" >/dev/null 2>&1; then
    if [ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" = "true" ]; then
        say "$(loc "контейнер $NAME уже запущен." "container $NAME is already running.")"
    else
        say "$(loc "контейнер $NAME существует, но остановлен — запускаю." \
            "container $NAME exists but is stopped — starting it.")"
        docker start "$NAME" >/dev/null
    fi
    RUNNING_PORT="$(published_port)"
    if [ -z "$RUNNING_PORT" ]; then
        die "$(loc "контейнер $NAME запущен без публикации порта — снаружи он недоступен.
  Пересоздайте его: docker rm -f $NAME && повторите этот скрипт." \
            "container $NAME runs without a published port — it is unreachable from outside.
  Recreate it: docker rm -f $NAME && re-run this script.")"
    fi
    say "$(loc "чтобы поставить заново с нуля: docker rm -f $NAME, затем повторите скрипт." \
        "to reinstall from scratch: docker rm -f $NAME, then re-run the script.")"
    finish "$RUNNING_PORT"
    exit 0
fi

say "$(loc "скачиваю образ $IMAGE" "pulling image $IMAGE")"
if ! PULL_ERR="$(docker pull "$IMAGE" 2>&1 >/dev/null)"; then
    if docker image inspect "$IMAGE" >/dev/null 2>&1; then
        say "$(loc 'обновить образ не удалось, запускаю уже скачанный.' \
            'could not update the image, starting the one already downloaded.')"
    else
        die "$(loc "не удалось скачать образ $IMAGE:" "failed to pull image $IMAGE:")
$PULL_ERR"
    fi
fi

GROUP_ARGS="--group-add $(socket_group)"

# Каталог данных НЕ монтируем: его назовёт пользователь в мастере, после чего
# приложение пересоздаст себя с этим -v само. Смонтировать что-то заранее —
# значит вернуть ту самую развилку, ради устранения которой мастер и появился.
#
# HSE_STUDIO__SERVER__PORT=8000 передаём явно, хотя свежий образ выставляет его и
# сам: на 8000 смотрит HEALTHCHECK, а по его результату мастер настройки решает,
# поднялся ли пересозданный контейнер. Образы, опубликованные до этой правки,
# слушают 17240 (порт нативного запуска) и без переменной остаются вечно
# unhealthy — настройка на них откатывалась бы всегда.
PORT_NOW="$FIRST_PORT"
ATTEMPT=1
while :; do
    if RUN_ERR="$(start_container "$PORT_NOW")"; then
        break
    fi
    # Контейнер, не сумевший опубликовать порт, остаётся в состоянии Created и
    # держит имя — следующая попытка упала бы уже на занятом имени.
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    case "$RUN_ERR" in
        *"address already in use"* | *"port is already allocated"* | *"Ports are not available"*)
            ATTEMPT=$((ATTEMPT + 1))
            if [ "$ATTEMPT" -gt "$PORT_ATTEMPTS" ]; then
                die "$(loc "порты с $FIRST_PORT по $PORT_NOW заняты. Освободите один или задайте свой:
    PORT=18500 sh install.sh" \
                    "ports $FIRST_PORT through $PORT_NOW are taken. Free one or set your own:
    PORT=18500 sh install.sh")"
            fi
            PORT_NOW=$((PORT_NOW + 1))
            say "$(loc "порт занят, пробую $PORT_NOW" "port taken, trying $PORT_NOW")"
            ;;
        *)
            die "$(loc 'docker run не смог запустить контейнер:' 'docker run failed to start the container:')
$RUN_ERR"
            ;;
    esac
done

say "$(loc "контейнер $NAME запущен на порту $PORT_NOW." "container $NAME is running on port $PORT_NOW.")"
finish "$PORT_NOW"
