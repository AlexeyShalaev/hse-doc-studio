"""Чистая часть апдейтера: команды docker, образы, разбор дайджестов. Без процессов и сети, поэтому проверяется тестами.

Только стандартная библиотека: апдейтер обязан запускаться без зависимостей приложения.
"""

from __future__ import annotations

import json
import re
import shlex
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from hse_doc_studio.infra.update.updater import (
    _extra_host_args,
    _group_args,
    _label_args,
    _mount_args,
    _ports_args,
    _restart_args,
)

ROLLBACK_TAG = "rollback-prev"
COSIGN_IMAGE = "ghcr.io/sigstore/cosign/cosign:v2.4.1"
COSIGN_ISSUER = "https://token.actions.githubusercontent.com"
COSIGN_IDENTITY = r"^https://github\.com/AlexeyShalaev/hse-doc-studio/\.github/workflows/publish\.yml@refs/tags/v.*$"
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")

# Опции контейнера, которые пересоздание через `docker run` не переносит: с ними обновление отказывается, а не
# теряет настройку молча. Значения по умолчанию докера (пустые, False, 0) за опцию не считаются.
_UNSUPPORTED_HOST = (
    "Privileged",
    "CapAdd",
    "CapDrop",
    "SecurityOpt",
    "Devices",
    "Tmpfs",
    "ReadonlyRootfs",
    "ShmSize",
    "Ulimits",
    "Sysctls",
    "PidMode",
    "IpcMode",
    "Runtime",
    "DeviceRequests",
)
_HOST_DEFAULTS: Mapping[str, object] = {"ShmSize": 67108864, "PidMode": "", "IpcMode": "private", "Runtime": "runc"}


def split_image(ref: str) -> tuple[str, str]:
    """`host:5000/ns/name:tag@sha256:..` -> (`host:5000/ns/name`, `tag`)."""
    ref = ref.split("@", 1)[0]
    last = ref.rsplit("/", 1)[-1]
    if ":" in last:
        repo, _, tag = ref.rpartition(":")
        return repo, tag
    return ref, "latest"


def target_ref(current_ref: str, version: str) -> str:
    """Тот же репозиторий, что у работающего контейнера, и тег новой версии."""
    return f"{split_image(current_ref)[0]}:{version}"


def rollback_ref(current_ref: str) -> str:
    return f"{split_image(current_ref)[0]}:{ROLLBACK_TAG}"


def is_version(value: str) -> bool:
    return bool(_VERSION.match(value))


def unsupported_options(container: Mapping[str, Any]) -> list[str]:
    host = container.get("HostConfig") or {}
    found: list[str] = []
    for key in _UNSUPPORTED_HOST:
        value = host.get(key)
        if value in (None, "", [], {}, False, 0) or value == _HOST_DEFAULTS.get(key):
            continue
        found.append(key)
    return found


def parse_digest_doc(raw: str, *, version: str) -> str | None:
    """Дайджест индекса образа из `image-digest.json` релиза; чужая версия или битый формат дают None."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or str(data.get("version", "")).lstrip("v") != version:
        return None
    digest = data.get("digest")
    return digest if isinstance(digest, str) and _DIGEST.match(digest) else None


def repo_digests(image_inspect: Mapping[str, Any], repo: str) -> list[str]:
    """Дайджесты скачанного образа для репозитория (`RepoDigests` хранит `repo@sha256:..`)."""
    out: list[str] = []
    for item in image_inspect.get("RepoDigests") or []:
        name, _, digest = str(item).partition("@")
        if name == repo and _DIGEST.match(digest):
            out.append(digest)
    return out


def digest_matches(image_inspect: Mapping[str, Any], repo: str, expected: str) -> bool:
    return expected in repo_digests(image_inspect, repo)


def cosign_verify_command(repo: str, digest: str) -> list[str]:
    """Проверка подписи keyless: подписал workflow publish.yml этого репозитория на теге релиза."""
    return [
        "run",
        "--rm",
        COSIGN_IMAGE,
        "verify",
        "--certificate-identity-regexp",
        COSIGN_IDENTITY,
        "--certificate-oidc-issuer",
        COSIGN_ISSUER,
        f"{repo}@{digest}",
    ]


def env_file_text(env: Iterable[str]) -> str:
    """Окружение api для одноразовых контейнеров. Строки без перевода строки внутри (иначе env-file ломается)."""
    lines = [e for e in env if "\n" not in e and not e.startswith(("HOSTNAME=", "PATH=", "HOME="))]
    return "\n".join(lines) + "\n"


def oneshot_command(
    image: str,
    command: Sequence[str],
    *,
    network: str,
    env_file: str,
    snapshot_volume: str | None = None,
    name: str | None = None,
) -> list[str]:
    """`docker run --rm` в сети api с его окружением: миграции, `db current`, снимок и восстановление."""
    args = ["run", "--rm", "--network", network, "--env-file", env_file]
    if name:
        args += ["--name", name]
    if snapshot_volume:
        args += ["-v", f"{snapshot_volume}:/snap"]
    return [*args, image, *command]


def _network_alias_args(container: Mapping[str, Any]) -> list[str]:
    """Имена в сети compose (сервис, контейнер): `docker run` сам их не добавляет, без них `api` не резолвится."""
    host = container.get("HostConfig") or {}
    mode = host.get("NetworkMode") or ""
    if mode in ("", "default", "bridge", "host", "none"):
        return []
    net = ((container.get("NetworkSettings") or {}).get("Networks") or {}).get(mode) or {}
    cid = str(container.get("Id") or "")[:12]
    args = ["--network", mode]
    for alias in net.get("Aliases") or []:
        if alias and alias != cid:
            args += ["--network-alias", alias]
    return args


def _health_args(config: Mapping[str, Any]) -> list[str]:
    health = config.get("Healthcheck") or {}
    test = health.get("Test") or []
    if test and test[0] == "NONE":
        # Проверка отключена явно (`healthcheck: disable: true` у раннера и апдейтера): без флага `docker run`
        # вернул бы проверку образа (curl :8000), и у сервиса без HTTP она вечно «unhealthy».
        return ["--no-healthcheck"]
    if not test:
        return []
    cmd = shlex.join(test[1:]) if test[0] == "CMD" else " ".join(test[1:])
    args = ["--health-cmd", cmd]
    for flag, key in (
        ("--health-interval", "Interval"),
        ("--health-timeout", "Timeout"),
        ("--health-start-period", "StartPeriod"),
    ):
        if health.get(key):
            args += [flag, f"{int(health[key]) // 1_000_000}ms"]
    if health.get("Retries"):
        args += ["--health-retries", str(health["Retries"])]
    return args


def _log_args(host: Mapping[str, Any]) -> list[str]:
    log = host.get("LogConfig") or {}
    driver = log.get("Type") or ""
    if not driver:
        return []
    args = ["--log-driver", str(driver)]
    for key, value in (log.get("Config") or {}).items():
        args += ["--log-opt", f"{key}={value}"]
    return args


def _env_for_recreate(config: Mapping[str, Any], image_env: Sequence[str]) -> list[str]:
    image_set = set(image_env)
    out: list[str] = []
    for entry in config.get("Env") or []:
        if entry in image_set or entry.startswith(("HOSTNAME=", "PATH=")):
            continue
        out += ["-e", entry]
    return out


def recreate_command(container: Mapping[str, Any], image_inspect: Mapping[str, Any], image_ref: str) -> list[str]:
    """`docker run -d ...`, воспроизводящий контейнер compose на другом образе. Аргументы без `docker`."""
    config = container.get("Config") or {}
    host = container.get("HostConfig") or {}
    name = str(container.get("Name") or "").lstrip("/")
    image_env = (image_inspect.get("Config") or {}).get("Env") or []
    cmd = ["run", "-d", "--name", name]
    cmd += _restart_args(host)
    cmd += _network_alias_args(container)
    cmd += _group_args(host)
    cmd += _extra_host_args(host)
    cmd += _ports_args(host)
    cmd += _mount_args(container.get("Mounts"), None)
    cmd += _label_args(config.get("Labels"))
    cmd += _health_args(config)
    cmd += _log_args(host)
    if config.get("User"):
        cmd += ["--user", str(config["User"])]
    if config.get("WorkingDir"):
        cmd += ["--workdir", str(config["WorkingDir"])]
    cmd += _env_for_recreate(config, image_env)
    entrypoint = config.get("Entrypoint")
    image_entrypoint = (image_inspect.get("Config") or {}).get("Entrypoint")
    if entrypoint and entrypoint != image_entrypoint:
        cmd += ["--entrypoint", str(entrypoint[0])]
    cmd.append(image_ref)
    command = config.get("Cmd")
    if command and command != (image_inspect.get("Config") or {}).get("Cmd"):
        cmd += [str(c) for c in command]
    return cmd


def parse_db_current(output: str) -> tuple[str | None, str | None]:
    """Вывод `hse-doc-studio db current`: строки `current: X` и `head: Y` (X может быть `-`)."""
    current = head = None
    for line in output.splitlines():
        key, _, value = line.partition(":")
        if key.strip() == "current":
            current = None if value.strip() in {"", "-"} else value.strip()
        elif key.strip() == "head":
            head = value.strip() or None
    return current, head


def schema_mismatch(version: str, current: str | None, head: str | None) -> str | None:
    """Почему образ `version` нельзя поставить откатом на эту базу (None: схема совпадает). head == ревизия."""
    if current is not None and current == head:
        return None
    return (
        f"{version} expects database schema {head or 'unknown'}, the database is at {current or 'none'}. Rolling back "
        "to it would break the data or the version would not start, so nothing was changed. Restore a backup taken on "
        "that version instead."
    )


def set_env_tag(text: str, version: str) -> str:
    """Подставляет `TAG=<version>` в содержимое `.env`; нет строки значит дописывает. Остальное не трогает."""
    lines = text.splitlines()
    found = False
    for i, line in enumerate(lines):
        if re.match(r"^\s*TAG\s*=", line):
            lines[i] = f"TAG={version}"
            found = True
    if not found:
        lines.append(f"TAG={version}")
    return "\n".join(lines) + "\n"
