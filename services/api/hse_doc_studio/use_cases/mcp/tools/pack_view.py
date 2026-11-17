"""Общее для тулов Студии шаблонов «вровень с интерфейсом»: вид ответа (`format`), подтверждение (`confirm`), счётчики.

Каждый тул отвечает компактным текстом для агента и структурным JSON (`format`: `text`, `json` или `both`), как
`pack_outcome`; опасное действие сначала описывает последствия (`confirm: false`) и выполняется только с
`confirm: true`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final

from hse_doc_studio.core.agent.entities import ToolResult
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.use_cases.mcp.tools._base import ArgumentError, bool_arg, jsonable, optional_text
from hse_doc_studio.use_cases.mcp.tools.pack_outcome_view import dump

LAYOUTS: Final = ("text", "json", "both")

FORMAT_PROP: Final = {
    "type": "string",
    "enum": list(LAYOUTS),
    "default": "text",
    "description": "Вид ответа: text (компактный текст, по умолчанию), json (структура) или both",
}
CONFIRM_PROP: Final = {
    "type": "boolean",
    "default": False,
    "description": "false: только описать последствия, ничего не менять; true: выполнить",
}


def layout_arg(args: Mapping[str, object], default: str = "text") -> str:
    raw = optional_text(args, "format") or default
    if raw not in LAYOUTS:
        raise ArgumentError(
            localized_error(
                f"format: ожидается одно из {', '.join(LAYOUTS)}, получено {raw!r}",
                f"format: one of {', '.join(LAYOUTS)} is expected, got {raw!r}",
            )
        )
    return raw


def layout_result(layout: str, text: str, data: object, *, truncated: bool = False) -> ToolResult:
    """Ответ в выбранном виде: компактный текст, структура или оба."""
    if layout == "text":
        return ToolResult.ok(text, truncated=truncated)
    if layout == "json":
        return ToolResult.ok(dump(jsonable(data)), truncated=truncated)
    return ToolResult.ok(dump({"text": text, "data": jsonable(data)}), truncated=truncated)


def confirmed(args: Mapping[str, object]) -> bool:
    return bool_arg(args, "confirm", False)


def clip_text(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + "\n…", True


def count_line(**counts: Any) -> str:
    return ", ".join(f"{k}: {v}" for k, v in counts.items())


def coded_error(code: str, ru: str, en: str, **ctx: object) -> ToolResult:
    """Отказ тула с кодом и подсказкой `hint` на языке интерфейса (там, где сценарий не бросает свою ошибку)."""
    return ToolResult.error(json.dumps({"code": code, **ctx, "hint": localized_error(ru, en)}, ensure_ascii=False))
