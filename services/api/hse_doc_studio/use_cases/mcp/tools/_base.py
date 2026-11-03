"""Общее для тулов MCP: базовый класс, разбор аргументов и сериализация ответа в JSON."""

from __future__ import annotations

import base64
import dataclasses
import json
from collections.abc import Mapping
from datetime import date, datetime
from enum import Enum
from pathlib import PurePath
from typing import Any, ClassVar
from uuid import UUID

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.mcp.protocols import IDependencyResolver

PROJECT_ID_SCHEMA: Mapping[str, Any] = {"type": "string", "description": "Идентификатор проекта (UUID)"}


class ArgumentError(ValueError):
    """Аргумент вызова отсутствует или неверен; превращается в код `invalid_arguments`."""


class McpTool:
    """Тул поверх сценариев. Сценарии берутся из контейнера при вызове: часть есть только на сервере."""

    spec: ClassVar[ToolSpec]
    kind: ClassVar[ToolKind]
    requires_project: ClassVar[bool] = True

    def __init__(self, deps: IDependencyResolver) -> None:
        self._deps = deps

    def definition(self) -> ToolDefinition:
        return ToolDefinition(spec=self.spec, kind=self.kind, handler=self, requires_project=self.requires_project)

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        raise NotImplementedError


def text_arg(args: Mapping[str, object], key: str, *, required: bool = True) -> str:
    raw = args.get(key)
    value = raw.strip() if isinstance(raw, str) else ""
    if required and not value:
        raise ArgumentError(localized_error(f"укажите параметр {key}", f"specify the {key} parameter"))
    return value


def optional_text(args: Mapping[str, object], key: str) -> str | None:
    return text_arg(args, key, required=False) or None


def uuid_arg(args: Mapping[str, object], key: str) -> UUID:
    value = text_arg(args, key)
    try:
        return UUID(value)
    except ValueError:
        raise ArgumentError(
            localized_error(f"{key}: ожидается UUID, получено {value!r}", f"{key}: a UUID is expected, got {value!r}")
        ) from None


def int_arg(args: Mapping[str, object], key: str, default: int, *, lo: int, hi: int) -> int:
    raw = args.get(key, default)
    if isinstance(raw, bool):
        return default
    if isinstance(raw, str) and raw.strip().lstrip("-").isdigit():
        raw = int(raw.strip())
    if not isinstance(raw, int | float):
        return default
    return max(lo, min(hi, int(raw)))


def bool_arg(args: Mapping[str, object], key: str, default: bool) -> bool:
    raw = args.get(key, default)
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes"}
    return raw if isinstance(raw, bool) else default


def jsonable(value: object) -> object:  # noqa: C901, PLR0911 — плоский разбор типов
    """Сущности (dataclass, перечисления, UUID, даты, пути) в простые типы JSON."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID | PurePath):
        return str(value)
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    if isinstance(value, Mapping):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        items = [jsonable(v) for v in value]
        return sorted(items, key=str) if isinstance(value, set | frozenset) else items
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return jsonable(model_dump(mode="json"))
    return value


def json_result(value: object, *, truncated: bool = False) -> ToolResult:
    return ToolResult.ok(json.dumps(jsonable(value), ensure_ascii=False, indent=1), truncated=truncated)


def project_schema(properties: Mapping[str, Any], required: tuple[str, ...] = ()) -> dict[str, Any]:
    """Схема аргументов тула проекта; `project_id` к ней добавляет каталог."""
    return {"type": "object", "properties": dict(properties), "required": list(required)}
