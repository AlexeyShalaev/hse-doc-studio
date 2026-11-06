"""Готовые команды запуска раннера с секретом: показываются один раз в ответе на создание или смену токена."""

from __future__ import annotations

from fastapi import Request

from hse_doc_studio.api.config import settings

RUNNER_DATA_DIR = "/var/lib/hse-runner"


def studio_base_url(request: Request) -> str:
    """Адрес Студии для раннера: public_url, иначе адрес, по которому пришёл запрос."""
    return (settings.auth.public_url or str(request.base_url)).rstrip("/")


def registration_command(base: str, secret: str) -> str:
    return f"HSE_RUNNER__API_URL={base} HSE_RUNNER__TOKEN={secret} hse-doc-studio runner"


def runner_token_command(base: str, secret: str) -> str:
    """`HSE_RUNNER__RUNNER_TOKEN` перекрывает сохранённую личность раннера (identity.json)."""
    return f"HSE_RUNNER__API_URL={base} HSE_RUNNER__RUNNER_TOKEN={secret} hse-doc-studio runner"


def runner_image() -> str:
    return f"{settings.image_base}:{settings.get_app_version()}"


def registration_docker_command(base: str, secret: str, *, env_name: str = "HSE_RUNNER__TOKEN") -> str:
    """Образ установки той же версии; каталог данных на хосте по тому же пути внутри и снаружи контейнера."""
    image = runner_image()
    return (
        "docker run -d --name hse-runner --restart unless-stopped"
        ' --group-add "$(stat -c %g /var/run/docker.sock)"'
        " -v /var/run/docker.sock:/var/run/docker.sock"
        f" -v {RUNNER_DATA_DIR}:{RUNNER_DATA_DIR}"
        f" -e HSE_RUNNER__API_URL={base} -e {env_name}={secret}"
        f" -e HSE_RUNNER__DATA_DIR={RUNNER_DATA_DIR}"
        f" {image} hse-doc-studio runner"
    )


def install_script_url(base: str) -> str:
    return f"{base}/api/runner/v1/install.sh"


def registration_script_command(
    base: str, secret: str, *, env_name: str = "HSE_RUNNER__TOKEN", macos: bool = False
) -> str:
    """Скрипт ставит службу; токен и адрес идут окружением команды, поэтому сам скрипт секретов не содержит.

    Linux ставит системную службу systemd (нужен root), macOS пользовательскую службу launchd (без sudo).
    """
    sudo = "" if macos else "sudo "
    env = f"HSE_RUNNER__API_URL={base} {env_name}={secret}"
    return f"curl -fsSL {install_script_url(base)} | {sudo}env {env} sh -s -- install"
