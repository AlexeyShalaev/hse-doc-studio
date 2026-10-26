from __future__ import annotations

import atexit
import functools
import os
import shutil
import tempfile
from pathlib import Path

# Всё, что git нужно от окружения. Остальное (HSE_STUDIO__*, ключи API, SSH_AUTH_SOCK,
# GIT_TRACE*, GIT_SSH*, GIT_EXEC_PATH и т.п.) родителя в git не попадает.
_ENV_ALLOW = frozenset(
    {
        "PATH",
        "TMPDIR",
        "TEMP",
        "TMP",
        "TZ",
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "CURL_CA_BUNDLE",
        "GIT_SSL_CAINFO",
        "GIT_SSL_CAPATH",
    }
)


@functools.lru_cache(maxsize=1)
def _private_dir() -> str | None:
    """Каталог на процесс для пустых заглушек конфига и хуков: посторонний не подложит туда файл."""
    try:
        path = tempfile.mkdtemp(prefix="hse-studio-git-")
    except OSError:
        return None
    atexit.register(shutil.rmtree, path, ignore_errors=True)
    return path


@functools.lru_cache(maxsize=1)
def empty_global_config() -> str:
    """Путь к настоящему пустому gitconfig для GIT_CONFIG_GLOBAL.

    Нейтрализует ~/.gitconfig пользователя (commit.gpgsign, хуки, алиасы). В отличие
    от /dev/null работает на всех платформах. Если временный каталог недоступен,
    остаётся `os.devnull`.
    """
    directory = _private_dir()
    if directory is None:
        return os.devnull
    path = Path(directory) / "empty.gitconfig"
    try:
        path.write_text("", encoding="utf-8")
    except OSError:
        return os.devnull
    return str(path)


@functools.lru_cache(maxsize=1)
def empty_hooks_dir() -> str:
    """Пустой каталог для core.hooksPath: свой на процесс, чтобы посторонний не подложил туда хук."""
    directory = _private_dir()
    if directory is None:
        return os.devnull
    hooks = Path(directory) / "hooks"
    try:
        hooks.mkdir()
    except OSError:
        return os.devnull
    return str(hooks)


def base_git_env() -> dict[str, str]:
    """Окружение для любого запуска git: белый список вместо копии os.environ.

    Копированное хранилище проекта недоверенное, а окружение сервера несёт секреты,
    поэтому git видит только PATH, прокси и CA, а конфигурация и язык фиксированы.
    """
    env = {key: value for key, value in os.environ.items() if key.upper() in _ENV_ALLOW}
    env["LC_ALL"] = "C"
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = empty_global_config()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    if os.name == "posix":
        # Контейнер работает без $HOME: даём git записываемый, иначе init/gc упираются в HOME=/.
        env["HOME"] = tempfile.gettempdir()
    return env


def hardened_git_config() -> list[str]:
    """Аргументы `-c`, которые перекрывают конфигурацию недоверенного хранилища.

    Конфиг `<project>/.hse-studio/git/config` приезжает вместе с проектом и мог бы
    запускать код через fsmonitor, хуки, sshCommand или credential helper.
    """
    return [
        "-c",
        f"core.hooksPath={empty_hooks_dir()}",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.sshCommand=",
        "-c",
        "credential.helper=",
        "-c",
        "protocol.ext.allow=never",
        "-c",
        "core.attributesFile=",
    ]
