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

# Адрес облачной Студии, к которой подключить эту (экран «Локальная версия» облака
# подставляет его сам): после запуска откроется экран подключения, а не главная.
CONNECT_SERVER="${HSE_STUDIO_CONNECT:-}"

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

# ── 2. Шрифты macOS ─────────────────────────────────────────────────────────

# Шаблоны просят Times New Roman, Arial, Courier New и Consolas: так выглядят
# документы по ГОСТ. Студия забирает их с машины сама, одноразовым контейнером с
# биндом системного каталога шрифтов. На macOS это не работает: Docker Desktop
# отдаёт контейнерам только /Users, /Volumes, /private, /tmp и /var/folders, а
# на бинд /System/Library/Fonts/Supplemental отвечает «mounts denied». Без шрифтов
# TeX долго ищет Arial (mktextfm) и ставит свободные замены.
#
# Поэтому здесь, на хосте, копируем ТОЛЬКО эти семейства с этой же машины в папку
# под домашним каталогом (её Docker Desktop отдаёт) и называем её Студии через
# HSE_STUDIO__FONTS__HOST_DIR. В образ и в репозиторий шрифты не попадают.
FONTS_STAGE="${HSE_STUDIO_FONTS_DIR:-$HOME/.hse-doc-studio/host-fonts}"
FONTS_HOST_DIR=""

# Файл шрифта в папку FONTS_STAGE (или в $2), если его там ещё нет.
copy_font() {
    [ -f "$1" ] || return 0
    _to="${2:-$FONTS_STAGE}"
    [ -e "$_to/${1##*/}" ] && return 0
    cp "$1" "$_to/" 2>/dev/null || true
}

# Сколько файлов шрифтов в каталоге $1.
count_fonts() {
    find "$1" -maxdepth 1 -type f \( -iname '*.ttf' -o -iname '*.otf' -o -iname '*.ttc' \) 2>/dev/null | wc -l | tr -d ' '
}

stage_mac_fonts() {
    [ "$OS" = "Darwin" ] || return 0
    mkdir -p "$FONTS_STAGE" 2>/dev/null || return 0
    # Сначала системные, потом общие и пользовательские: первым найденный файл и остаётся.
    for _dir in /System/Library/Fonts/Supplemental /Library/Fonts "$HOME/Library/Fonts"; do
        [ -d "$_dir" ] || continue
        for _font in "$_dir"/"Times New Roman"*.ttf "$_dir/Arial.ttf" "$_dir/Arial Bold.ttf" \
            "$_dir/Arial Italic.ttf" "$_dir/Arial Bold Italic.ttf" "$_dir"/"Courier New"*.ttf \
            "$_dir"/[Cc]onsola*.ttf; do
            copy_font "$_font"
        done
    done
    # Consolas в macOS нет, его приносит Microsoft Office: шрифты лежат внутри приложений.
    for _font in /Applications/Microsoft*.app/Contents/Resources/DFonts/[Cc]onsola*.ttf; do
        copy_font "$_font"
    done
    _count="$(count_fonts "$FONTS_STAGE")"
    if [ "$_count" -gt 0 ]; then
        FONTS_HOST_DIR="$FONTS_STAGE"
        say "$(loc "шрифты для документов (Times New Roman, Arial, Courier New, Consolas, что нашлось: $_count): $FONTS_STAGE" \
            "fonts for documents (Times New Roman, Arial, Courier New, Consolas, found: $_count): $FONTS_STAGE")"
    else
        say "$(loc 'Times New Roman и Arial на этой машине не нашлись: документы соберутся со свободными заменами.
  Шрифты можно загрузить потом: Настройки → Шрифты.' \
            'Times New Roman and Arial were not found on this machine: documents will build with free substitutes.
  You can upload fonts later: Settings → Fonts.')"
    fi
}

# Уже установленная Студия: env контейнера не поменять без пересоздания, поэтому
# недостающие шрифты кладём прямо в её папку шрифтов (<папка данных>/fonts), ту
# самую, что монтируется в сборку. Только добавляем: свои шрифты человека не трогаем.
adopt_into_existing() {
    [ -n "$FONTS_HOST_DIR" ] || return 0
    _data="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$NAME" 2>/dev/null |
        sed -n 's/^HSE_STUDIO__HOST_DATA_DIR=//p' | head -n 1)"
    if [ -z "$_data" ] || [ ! -d "$_data" ]; then
        say "$(loc "папка данных $NAME ещё не выбрана или не найдена: шрифты Студия возьмёт после мастера настройки, если контейнер поставлен этим скриптом заново." \
            "the data folder of $NAME is not chosen yet or not found: the Studio picks the fonts up after the setup wizard if the container is installed by this script anew.")"
        return 0
    fi
    mkdir -p "$_data/fonts" 2>/dev/null || return 0
    _before="$(count_fonts "$_data/fonts")"
    for _font in "$FONTS_STAGE"/*; do
        copy_font "$_font" "$_data/fonts"
    done
    _added=$(($(count_fonts "$_data/fonts") - _before))
    if [ "$_added" -gt 0 ]; then
        say "$(loc "добавил шрифтов в $_data/fonts: $_added. Следующие сборки возьмут их сами." \
            "added fonts to $_data/fonts: $_added. Next builds pick them up by themselves.")"
    fi
}

# ── 3. Запуск ───────────────────────────────────────────────────────────────

# Семейство ОС для списка подключённых Студий в облаке (внутри контейнера оно неизвестно).
device_os() {
    case "$OS" in
        Darwin) echo macos ;;
        Linux) echo linux ;;
        *) echo "" ;;
    esac
}

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
        -e "HSE_STUDIO__DEVICE_NAME=$(hostname -s 2>/dev/null || hostname)" \
        -e "HSE_STUDIO__DEVICE_OS=$(device_os)" \
        -e "HSE_STUDIO__FONTS__HOST_DIR=$FONTS_HOST_DIR" \
        $GROUP_ARGS \
        "$IMAGE" 2>&1 >/dev/null
}

# Порт хоста, на котором контейнер реально опубликован. Спрашиваем докер, а не
# помним своё: контейнер мог остаться от прошлого запуска с другим портом.
published_port() {
    docker port "$NAME" 8000/tcp 2>/dev/null | head -n 1 | sed 's/.*://'
}

# ── 4. Здоровье и браузер ───────────────────────────────────────────────────

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

# Адрес экрана подключения к серверу; пусто, если адрес не задан или подозрителен.
# Пропускаем только https://host[:port] (http только для localhost): строка идёт
# в браузер как есть, без кодирования, поэтому лишних символов в ней быть не должно.
connect_path() {
    case "$CONNECT_SERVER" in
        "") return 0 ;;
        *[!A-Za-z0-9.:/-]*) ;;
        https://?* | http://localhost* | http://127.0.0.1*)
            printf '/connect?server=%s' "${CONNECT_SERVER%/}"
            return 0
            ;;
    esac
    say "$(loc "HSE_STUDIO_CONNECT пропущен: нужен адрес вида https://studio.example.org" \
        "HSE_STUDIO_CONNECT ignored: expected an address like https://studio.example.org")" >&2
}

finish() {
    _url="http://localhost:$1$(connect_path)"
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
stage_mac_fonts

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
    adopt_into_existing
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
