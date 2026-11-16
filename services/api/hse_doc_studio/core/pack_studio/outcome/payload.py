"""Результат в виде словаря контракта: тот же вид, что у ответа `PackOutcome` (кроме полей границы запроса)."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from enum import Enum
from typing import Any


def to_json(value: Any) -> Any:
    """Рекурсивно: dataclass в словарь, кортеж и список в список, перечисление в значение; остальное как есть."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_json(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): to_json(item) for key, item in value.items()}
    if isinstance(value, tuple | list | set | frozenset):
        return [to_json(item) for item in value]
    return value
