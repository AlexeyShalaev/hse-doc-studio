"""Откуда взято значение настройки установки: окружение, правка админа или умолчание."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum


class SettingSource(StrEnum):
    env = "env"
    admin = "admin"
    default = "default"


@dataclass(frozen=True)
class SettingDescription:
    """`locked`: значение задано окружением, из интерфейса не меняется."""

    key: str
    source: SettingSource
    locked: bool


def describe_setting(key: str, *, stored: Collection[str], locked: Collection[str]) -> SettingDescription:
    """Окружение побеждает запись админа, запись админа побеждает умолчание."""
    if key in locked:
        return SettingDescription(key, SettingSource.env, True)
    return SettingDescription(key, SettingSource.admin if key in stored else SettingSource.default, False)
