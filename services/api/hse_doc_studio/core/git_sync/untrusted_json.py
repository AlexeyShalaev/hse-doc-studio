"""Разбор JSON из чужой ветки: вложенность ограничена, любой отказ это ValueError.

`json.loads` на документе в десятки тысяч вложенных массивов бросает RecursionError (это RuntimeError, а не
ValueError), и обычное «не разобралось» превращалось в падение с общей ошибкой. Файлы состояния Студии вложены
на пять-шесть уровней, поэтому глубокий документ это либо мусор, либо попытка обойти рекурсивные обходы слияния.
"""

from __future__ import annotations

import json
from typing import Any, Final

MAX_JSON_DEPTH: Final = 64


def loads_untrusted(raw: bytes) -> Any:
    """Документ из байтов (BOM допускается); ValueError, если это не JSON или он вложен глубже MAX_JSON_DEPTH."""
    try:
        value = json.loads(raw.decode("utf-8-sig"))
    except RecursionError as exc:
        raise ValueError("JSON is nested too deeply") from exc
    if _too_deep(value):
        raise ValueError("JSON is nested too deeply")
    return value


def _too_deep(value: Any) -> bool:
    pending: list[tuple[Any, int]] = [(value, 1)]
    while pending:
        node, depth = pending.pop()
        if isinstance(node, dict):
            children: Any = node.values()
        elif isinstance(node, list):
            children = node
        else:
            continue
        if depth > MAX_JSON_DEPTH:
            return True
        pending.extend((child, depth + 1) for child in children)
    return False
