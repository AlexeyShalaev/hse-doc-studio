"""Формы настроек и журнала MCP-сервера (docs/design/mcp.md, раздел 4)."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, Field

from hse_doc_studio.api.schemas.common import StrictModel

McpToolGroupName = Literal[
    "account", "projects", "files", "build", "checks", "review", "history", "submission", "admin"
]
McpToolKindName = Literal["read", "write", "exec", "ask"]
McpCallOutcomeName = Literal["ok", "error", "denied"]


class McpToolItem(StrictModel):
    name: str
    group: McpToolGroupName
    kind: McpToolKindName
    description: str
    dangerous: bool
    admin: bool
    enabled: bool


class McpSettingsResponse(StrictModel):
    enabled: bool
    disabled_tools: list[str]
    disabled_groups: list[McpToolGroupName]
    enabled_dangerous: list[str]
    # Адрес сервера относительно корня Студии.
    endpoint_path: str
    tools: list[McpToolItem]


class UpdateMcpSettingsRequest(StrictModel):
    """`null` значит «не менять»; списки заменяются целиком."""

    enabled: bool | None = None
    disabled_tools: list[str] | None = Field(default=None, max_length=200)
    disabled_groups: list[McpToolGroupName] | None = None
    enabled_dangerous: list[str] | None = Field(default=None, max_length=200)


class McpCallItem(StrictModel):
    at: AwareDatetime
    tool: str
    outcome: McpCallOutcomeName
    duration_ms: int
    actor_id: str | None
    actor_name: str | None
    project_id: str | None
    error_code: str | None
    client: str | None
    arg_keys: list[str]


class McpInfoResponse(StrictModel):
    """Сведения для подключения клиента: включён ли MCP и какие тулы видит этот человек."""

    enabled: bool
    mode: Literal["local", "server"]
    endpoint_path: str
    # Нужна ли область токена (облако) и какая.
    token_scope: str | None
    tools: list[str]
