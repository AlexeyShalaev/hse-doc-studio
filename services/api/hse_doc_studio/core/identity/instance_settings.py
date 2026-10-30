"""Название и адрес установки, настройки сборки: ключи в instance_settings, окружение и умолчания."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

KEY_NAME = "instance.name"
KEY_PUBLIC_URL = "instance.public_url"
KEY_DOCS_URL = "instance.docs_url"
KEY_BUILD_TIMEOUT_S = "build.timeout_s"
KEY_ARTIFACT_RETENTION_DAYS = "build.artifact_retention_days"

INSTANCE_KEYS = (KEY_NAME, KEY_PUBLIC_URL, KEY_DOCS_URL)
BUILD_KEYS = (KEY_BUILD_TIMEOUT_S, KEY_ARTIFACT_RETENTION_DAYS)

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

    def locked_keys(self) -> frozenset[str]:
        pairs = (
            (KEY_NAME, self.name),
            (KEY_PUBLIC_URL, self.public_url),
            (KEY_DOCS_URL, self.docs_url),
            (KEY_BUILD_TIMEOUT_S, self.build_timeout_s),
            (KEY_ARTIFACT_RETENTION_DAYS, self.artifact_retention_days),
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
