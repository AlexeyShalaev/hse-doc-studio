"""Вычёркивание секретов из деталей события аудита."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

REDACTED = "[redacted]"
_SECRET_MARKERS = ("password", "passwd", "token", "secret", "key", "authorization", "cookie")


def is_secret_key(name: str) -> bool:
    lowered = name.lower()
    return any(marker in lowered for marker in _SECRET_MARKERS)


def redact(value: Any) -> Any:
    """Копия значения, где под секретными ключами любой вложенности стоит `[redacted]`; прочее приводится к JSON."""
    if isinstance(value, Mapping):
        return {str(key): REDACTED if is_secret_key(str(key)) else redact(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [redact(item) for item in value]
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return str(value)
