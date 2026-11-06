#!/bin/sh
# hse-doc-studio: установка раннера как службы (systemd на Linux, launchd на macOS).
#
# Скрипт отдаётся Студией без секретов: токен, адрес Студии и остальное берутся из окружения команды.
# Прочитать его до запуска можно так: curl -fsSL <адрес>/api/runner/v1/install.sh -o install.sh && less install.sh
#
# Использование:  sh install.sh install | uninstall | status | plan   [--purge]
#
#   install     записать описание службы и файл окружения, скачать образ, запустить и включить автозапуск;
#               повторный запуск безопасен: файлы перезаписываются теми же значениями, служба перезапускается
#   uninstall   остановить и убрать службу и файл окружения; с --purge ещё контейнер, образ и каталог данных
#   status      показать состояние службы
#   plan        напечатать, что сделает install, и ничего не менять (то же, что HSE_RUNNER_DRY_RUN=1)
#
# Окружение:
#   HSE_RUNNER__API_URL        адрес Студии (обязательно для install)
#   HSE_RUNNER__TOKEN          токен регистрации (нужен при первой установке; потом раннер хранит свой в каталоге данных)
#   HSE_RUNNER__RUNNER_TOKEN   токен самого раннера после ротации (перекрывает сохранённый)
#   HSE_RUNNER__NAME           имя в списке раннеров (по умолчанию имя хоста)
#   HSE_RUNNER__CONCURRENCY    сколько задач одновременно (по умолчанию 1)
#   HSE_RUNNER_IMAGE           образ раннера (по умолчанию образ той же версии, что и Студия)
#   HSE_RUNNER_SERVICE         имя службы и контейнера (по умолчанию hse-runner)
#   HSE_RUNNER_DATA_DIR        каталог данных на хосте (Linux /var/lib/hse-runner, macOS ~/.hse-runner)
#   HSE_RUNNER_DRY_RUN=1       только напечатать действия
#
# POSIX sh: на Debian и Ubuntu /bin/sh это dash, массивов и [[ ]] нет.
set -eu

IMAGE="${HSE_RUNNER_IMAGE:-@@IMAGE@@}"
SERVICE="${HSE_RUNNER_SERVICE:-hse-runner}"
DRY_RUN="${HSE_RUNNER_DRY_RUN:-0}"
OS="$(uname -s)"

say() { printf '%s\n' "$*"; }
die() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

# Команды, меняющие систему, идут только через run: в режиме plan они печатаются, а не выполняются.
run() {
    if [ "$DRY_RUN" = 1 ]; then
        say "  would run: $*"
    else
        # stdin команд закрыт: при запуске через `sh -s` скрипт читается из stdin, и команда не должна съесть его остаток.
        "$@" </dev/null
    fi
}

case "$OS" in
    Linux)
        DATA_DIR="${HSE_RUNNER_DATA_DIR:-/var/lib/hse-runner}"
        UNIT="/etc/systemd/system/$SERVICE.service"
        ENV_FILE="/etc/hse-runner/$SERVICE.env"
        ;;
    Darwin)
        DATA_DIR="${HSE_RUNNER_DATA_DIR:-$HOME/.hse-runner}"
        UNIT="$HOME/Library/LaunchAgents/ru.hse-doc-studio.$SERVICE.plist"
        ENV_FILE="$HOME/.hse-runner/$SERVICE.env"
        LABEL="ru.hse-doc-studio.$SERVICE"
        ;;
    *) die "unsupported OS: $OS (Linux and macOS only; on other systems use the docker run command)" ;;
esac

need_docker() {
    command -v docker >/dev/null 2>&1 || {
        if [ "$DRY_RUN" = 1 ]; then
            say "  warning: docker not found; install would stop here"
            return 0
        fi
        die "docker not found. The runner runs as a container: install Docker (https://docs.docker.com/engine/install/) and run this again."
    }
    if [ "$DRY_RUN" != 1 ]; then
        docker info >/dev/null 2>&1 </dev/null || die "docker is installed but not reachable for this user (daemon stopped, or no permission: try sudo)"
    fi
}

docker_sock_gid() {
    [ "$OS" = Linux ] && [ -S /var/run/docker.sock ] && stat -c %g /var/run/docker.sock 2>/dev/null || true
}

# Содержимое файла окружения. Токены сюда попадают только из окружения команды и лежат с правами 0600.
env_body() {
    say "HSE_RUNNER__API_URL=$HSE_RUNNER__API_URL"
    say "HSE_RUNNER__DATA_DIR=$DATA_DIR"
    say "HSE_RUNNER__CONCURRENCY=${HSE_RUNNER__CONCURRENCY:-1}"
    [ -z "${HSE_RUNNER__NAME:-}" ] || say "HSE_RUNNER__NAME=$HSE_RUNNER__NAME"
    [ -z "${HSE_RUNNER__TOKEN:-}" ] || say "HSE_RUNNER__TOKEN=$HSE_RUNNER__TOKEN"
    [ -z "${HSE_RUNNER__RUNNER_TOKEN:-}" ] || say "HSE_RUNNER__RUNNER_TOKEN=$HSE_RUNNER__RUNNER_TOKEN"
}

docker_args() {
    gid="$(docker_sock_gid)"
    group=""
    [ -z "$gid" ] || group="--group-add $gid"
    # shellcheck disable=SC2086
    say "run --rm --name $SERVICE --env-file $ENV_FILE $group -v /var/run/docker.sock:/var/run/docker.sock -v $DATA_DIR:$DATA_DIR $IMAGE hse-doc-studio runner"
}

write_env() {
    if [ "$DRY_RUN" = 1 ]; then
        say "  would write $ENV_FILE (mode 0600) with: $(env_body | sed 's/\(TOKEN=\).*/\1***/' | tr '\n' ' ')"
        return 0
    fi
    dir="$(dirname "$ENV_FILE")"
    mkdir -p "$dir" "$DATA_DIR"
    umask 077
    env_body >"$ENV_FILE.tmp"
    chmod 600 "$ENV_FILE.tmp"
    mv "$ENV_FILE.tmp" "$ENV_FILE"
}

write_linux_unit() {
    # shellcheck disable=SC2046
    body="[Unit]
Description=hse-doc-studio runner
Requires=docker.service
After=docker.service network-online.target

[Service]
Restart=always
RestartSec=5
ExecStartPre=-$(command -v docker || say docker) rm -f $SERVICE
ExecStart=$(command -v docker || say docker) $(docker_args)
ExecStop=$(command -v docker || say docker) stop $SERVICE

[Install]
WantedBy=multi-user.target"
    if [ "$DRY_RUN" = 1 ]; then
        say "  would write $UNIT:"
        say "$body" | sed 's/^/    | /'
        return 0
    fi
    printf '%s\n' "$body" >"$UNIT.tmp"
    mv "$UNIT.tmp" "$UNIT"
}

write_mac_plist() {
    docker_bin="$(command -v docker || say docker)"
    args=""
    for a in $(docker_args); do
        args="$args
        <string>$a</string>"
    done
    body="<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$docker_bin</string>$args
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$DATA_DIR/service.log</string>
    <key>StandardErrorPath</key><string>$DATA_DIR/service.log</string>
</dict>
</plist>"
    if [ "$DRY_RUN" = 1 ]; then
        say "  would write $UNIT:"
        say "$body" | sed 's/^/    | /'
        return 0
    fi
    mkdir -p "$(dirname "$UNIT")"
    printf '%s\n' "$body" >"$UNIT.tmp"
    mv "$UNIT.tmp" "$UNIT"
}

cmd_plan_header() {
    say "hse-doc-studio runner: $1"
    say "  service : $SERVICE ($OS)"
    say "  image   : $IMAGE"
    say "  studio  : ${HSE_RUNNER__API_URL:-}"
    say "  data    : $DATA_DIR"
    say "  unit    : $UNIT"
    say "  env file: $ENV_FILE"
}

cmd_install() {
    [ -n "${HSE_RUNNER__API_URL:-}" ] || die "set HSE_RUNNER__API_URL to the Studio address"
    cmd_plan_header install
    if [ "$OS" = Linux ] && [ "$DRY_RUN" != 1 ]; then
        [ "$(id -u)" = 0 ] || die "run as root (sudo): the unit is written to /etc/systemd/system"
        command -v systemctl >/dev/null 2>&1 || die "systemd not found; use the docker run command instead"
    fi
    need_docker
    if [ -z "${HSE_RUNNER__TOKEN:-}" ] && [ -z "${HSE_RUNNER__RUNNER_TOKEN:-}" ] && [ ! -f "$DATA_DIR/identity.json" ]; then
        [ "$DRY_RUN" = 1 ] || die "no token: set HSE_RUNNER__TOKEN (registration token), or reinstall over an existing runner"
    fi
    say "1/4 pull image"
    run docker pull "$IMAGE"
    say "2/4 write environment file"
    write_env
    say "3/4 write service definition"
    if [ "$OS" = Linux ]; then write_linux_unit; else write_mac_plist; fi
    say "4/4 start and enable"
    if [ "$OS" = Linux ]; then
        run systemctl daemon-reload
        run systemctl enable "$SERVICE"
        run systemctl restart "$SERVICE"
    else
        run launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
        run launchctl bootstrap "gui/$(id -u)" "$UNIT"
        run launchctl kickstart -k "gui/$(id -u)/$LABEL"
    fi
    say "done. The runner appears online in the Studio admin page shortly."
}

cmd_uninstall() {
    cmd_plan_header uninstall
    if [ "$OS" = Linux ]; then
        if [ "$DRY_RUN" != 1 ] && [ "$(id -u)" != 0 ]; then die "run as root (sudo)"; fi
        run systemctl disable --now "$SERVICE" 2>/dev/null || true
        run rm -f "$UNIT" "$ENV_FILE"
        run systemctl daemon-reload
    else
        run launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
        run rm -f "$UNIT" "$ENV_FILE"
    fi
    if command -v docker >/dev/null 2>&1; then
        run docker rm -f "$SERVICE" >/dev/null 2>&1 || true
    fi
    if [ "${PURGE:-0}" = 1 ]; then
        run docker rmi "$IMAGE" 2>/dev/null || true
        run rm -rf "$DATA_DIR"
        say "data directory removed: $DATA_DIR"
    else
        say "kept the data directory $DATA_DIR (the runner identity); add --purge to remove it"
    fi
    say "done. Revoke the runner in the Studio admin page if it is no longer needed."
}

cmd_status() {
    if [ "$OS" = Linux ]; then
        systemctl status "$SERVICE" --no-pager 2>&1 || true
    else
        launchctl print "gui/$(id -u)/$LABEL" 2>&1 | head -20 || true
    fi
}

ACTION="${1:-}"
PURGE=0
[ "${2:-}" != "--purge" ] || PURGE=1
case "$ACTION" in
    install) cmd_install ;;
    uninstall) cmd_uninstall ;;
    status) cmd_status ;;
    plan)
        DRY_RUN=1
        cmd_install
        ;;
    *) die "usage: sh install.sh install | uninstall [--purge] | status | plan" ;;
esac
