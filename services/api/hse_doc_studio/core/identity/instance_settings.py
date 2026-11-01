"""Название и адрес установки, настройки сборки: ключи в instance_settings, окружение и умолчания."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

from hse_doc_studio.core.jobs.routing import PERSONAL_MAX_PER_USER_LIMIT, PERSONAL_WAIT_MAX_S, PersonalRunnerSettings

KEY_NAME = "instance.name"
KEY_PUBLIC_URL = "instance.public_url"
KEY_DOCS_URL = "instance.docs_url"
KEY_BUILD_TIMEOUT_S = "build.timeout_s"
KEY_ARTIFACT_RETENTION_DAYS = "build.artifact_retention_days"
KEY_PERSONAL_ENABLED = "runners.personal_enabled"
KEY_PERSONAL_WAIT_S = "runners.personal_wait_s"
KEY_PERSONAL_MAX_PER_USER = "runners.personal_max_per_user"

INSTANCE_KEYS = (KEY_NAME, KEY_PUBLIC_URL, KEY_DOCS_URL)
BUILD_KEYS = (KEY_BUILD_TIMEOUT_S, KEY_ARTIFACT_RETENTION_DAYS)
PERSONAL_RUNNER_KEYS = (KEY_PERSONAL_ENABLED, KEY_PERSONAL_WAIT_S, KEY_PERSONAL_MAX_PER_USER)
PERSONAL_WAIT_RANGE = (0, PERSONAL_WAIT_MAX_S)
PERSONAL_MAX_PER_USER_RANGE = (1, PERSONAL_MAX_PER_USER_LIMIT)

DEFAULT_NAME = "HSE Doc Studio"
DEFAULT_BUILD_TIMEOUT_S = 600
DEFAULT_ARTIFACT_RETENTION_DAYS = 30
NAME_MAX = 120
URL_MAX = 2048
BUILD_TIMEOUT_RANGE = (30, 3600)
ARTIFACT_RETENTION_RANGE = (1, 365)
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1"})


@dataclass(frozen=True)
class InstanceSettings:
    name: str
    public_url: str
    docs_url: str | None


@dataclass(frozen=True)
class BuildSettings:
    timeout_s: int
    artifact_retention_days: int


@dataclass(frozen=True)
class InstanceEnvOverrides:
    """Значения из окружения: заданное (не None) побеждает БД и в интерфейсе только для чтения."""

    name: str | None = None
    public_url: str | None = None
    docs_url: str | None = None
    build_timeout_s: int | None = None
    artifact_retention_days: int | None = None
    personal_runners_enabled: bool | None = None
    personal_runner_wait_s: int | None = None
    personal_runners_max_per_user: int | None = None

    def locked_keys(self) -> frozenset[str]:
        pairs = (
            (KEY_NAME, self.name),
            (KEY_PUBLIC_URL, self.public_url),
            (KEY_DOCS_URL, self.docs_url),
            (KEY_BUILD_TIMEOUT_S, self.build_timeout_s),
            (KEY_ARTIFACT_RETENTION_DAYS, self.artifact_retention_days),
            (KEY_PERSONAL_ENABLED, self.personal_runners_enabled),
            (KEY_PERSONAL_WAIT_S, self.personal_runner_wait_s),
            (KEY_PERSONAL_MAX_PER_USER, self.personal_runners_max_per_user),
        )
        return frozenset(key for key, value in pairs if value is not None)


def _text(values: Mapping[str, object], key: str) -> str | None:
    raw = values.get(key)
    return raw.strip() if isinstance(raw, str) and raw.strip() else None


def _number(values: Mapping[str, object], key: str, bounds: tuple[int, int], default: int) -> int:
    raw = values.get(key)
    if isinstance(raw, int) and not isinstance(raw, bool) and bounds[0] <= raw <= bounds[1]:
        return raw
    return default


def effective_instance_settings(values: Mapping[str, object], env: InstanceEnvOverrides) -> InstanceSettings:
    return InstanceSettings(
        name=env.name or _text(values, KEY_NAME) or DEFAULT_NAME,
        public_url=env.public_url or _text(values, KEY_PUBLIC_URL) or "",
        docs_url=env.docs_url or _text(values, KEY_DOCS_URL),
    )


def effective_build_settings(values: Mapping[str, object], env: InstanceEnvOverrides) -> BuildSettings:
    return BuildSettings(
        timeout_s=env.build_timeout_s
        or _number(values, KEY_BUILD_TIMEOUT_S, BUILD_TIMEOUT_RANGE, DEFAULT_BUILD_TIMEOUT_S),
        artifact_retention_days=env.artifact_retention_days
        or _number(values, KEY_ARTIFACT_RETENTION_DAYS, ARTIFACT_RETENTION_RANGE, DEFAULT_ARTIFACT_RETENTION_DAYS),
    )


def effective_personal_runner_settings(
    values: Mapping[str, object], env: InstanceEnvOverrides
) -> PersonalRunnerSettings:
    """Личные раннеры: окружение побеждает БД; `False` и `0` из окружения тоже значения, а не «не задано»."""
    defaults = PersonalRunnerSettings()
    raw_enabled = values.get(KEY_PERSONAL_ENABLED)
    stored_enabled = raw_enabled if isinstance(raw_enabled, bool) else defaults.enabled
    return PersonalRunnerSettings(
        enabled=env.personal_runners_enabled if env.personal_runners_enabled is not None else stored_enabled,
        wait_s=env.personal_runner_wait_s
        if env.personal_runner_wait_s is not None
        else _number(values, KEY_PERSONAL_WAIT_S, PERSONAL_WAIT_RANGE, defaults.wait_s),
        max_per_user=env.personal_runners_max_per_user
        if env.personal_runners_max_per_user is not None
        else _number(values, KEY_PERSONAL_MAX_PER_USER, PERSONAL_MAX_PER_USER_RANGE, defaults.max_per_user),
    )


def is_valid_url(value: str, *, secure_only: bool) -> bool:
    """Адрес http(s) с хостом; для публичного адреса http допустим только на localhost."""
    if len(value) > URL_MAX:
        return False
    try:
        parts = urlsplit(value)
        host = parts.hostname
    except ValueError:
        return False
    if not host or parts.scheme not in {"http", "https"}:
        return False
    return parts.scheme == "https" or not secure_only or host in _LOCAL_HOSTS
