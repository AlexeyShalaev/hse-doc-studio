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

OS="$(uname -s)"
HTTP_TOOL=""

say() { printf '%s\n' "$*"; }
die() {
    printf 'ошибка: %s\n' "$*" >&2
    exit 1
}

# ── 1. Докер ────────────────────────────────────────────────────────────────

check_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        if [ "$OS" = "Darwin" ]; then
            die "не найден docker. Поставьте Docker Desktop: https://www.docker.com/products/docker-desktop/"
        fi
        die "не найден docker. Поставьте Docker Engine: https://docs.docker.com/engine/install/"
    fi

    # `docker info` вместо `docker version`: второй отвечает и без демона —
    # клиент печатает свою версию и молча выходит с нулём.
    if _err="$(docker info 2>&1 >/dev/null)"; then
        return 0
    fi
    case "$_err" in
        *"permission denied"*)
            die "нет доступа к докеру от текущего пользователя.
  Добавьте себя в группу docker и перелогиньтесь:
    sudo usermod -aG docker \$USER"
            ;;
    esac
    if [ "$OS" = "Darwin" ]; then
        die "демон докера не отвечает — запустите Docker Desktop и повторите.
$_err"
    fi
    die "демон докера не отвечает — запустите его (sudo systemctl start docker) и повторите.
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
        say "ни curl, ни wget не найдены — проверить готовность нечем, открываю адрес как есть."
    elif wait_healthy "$1"; then
        say "приложение отвечает."
    else
        say "приложение не ответило за ${HEALTH_TIMEOUT}с. Посмотрите логи: docker logs $NAME"
    fi
    open_browser "$_url" || say "браузер открыть нечем — откройте адрес вручную."
    say ""
    say "  $_url"
    say ""
    say "При первом запуске приложение спросит папку для ваших файлов и перезапустится"
    say "само — вкладку можно не закрывать, она дождётся."
    say ""
    say "  логи:       docker logs -f $NAME"
    say "  остановить: docker stop $NAME"
    say "  удалить:    docker rm -f $NAME"
}

# ── Сценарий ────────────────────────────────────────────────────────────────

check_docker
pick_http_tool

if [ ! -e "$DOCKER_SOCK" ]; then
    # Смонтировать несуществующий путь докер не откажется — он молча создаст
    # каталог, и приложение получит вместо сокета пустую папку.
    die "не найден docker-сокет $DOCKER_SOCK.
  Docker Desktop: включите «Allow the default Docker socket to be used» в настройках.
  Colima/Rancher: укажите свой путь, например
    DOCKER_SOCK=\$HOME/.colima/default/docker.sock sh install.sh"
fi

# Уже установлено — не пересоздаём молча: у существующего контейнера может быть
# выбранная пользователем папка данных, и потерять её из-за повторного запуска
# скрипта было бы худшим, что этот скрипт умеет.
if docker inspect "$NAME" >/dev/null 2>&1; then
    if [ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" = "true" ]; then
        say "контейнер $NAME уже запущен."
    else
        say "контейнер $NAME существует, но остановлен — запускаю."
        docker start "$NAME" >/dev/null
    fi
    RUNNING_PORT="$(published_port)"
    if [ -z "$RUNNING_PORT" ]; then
        die "контейнер $NAME запущен без публикации порта — снаружи он недоступен.
  Пересоздайте его: docker rm -f $NAME && повторите этот скрипт."
    fi
    say "чтобы поставить заново с нуля: docker rm -f $NAME, затем повторите скрипт."
    finish "$RUNNING_PORT"
    exit 0
fi

say "скачиваю образ $IMAGE"
if ! PULL_ERR="$(docker pull "$IMAGE" 2>&1 >/dev/null)"; then
    if docker image inspect "$IMAGE" >/dev/null 2>&1; then
        say "обновить образ не удалось, запускаю уже скачанный."
    else
        die "не удалось скачать образ $IMAGE:
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
                die "порты с $FIRST_PORT по $PORT_NOW заняты. Освободите один или задайте свой:
    PORT=18500 sh install.sh"
            fi
            PORT_NOW=$((PORT_NOW + 1))
            say "порт занят, пробую $PORT_NOW"
            ;;
        *)
            die "docker run не смог запустить контейнер:
$RUN_ERR"
            ;;
    esac
done

say "контейнер $NAME запущен на порту $PORT_NOW."
finish "$PORT_NOW"
