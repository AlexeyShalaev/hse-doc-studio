"""Ответы настроек и журнала MCP: одна форма для админки облака и настроек локальной Студии."""

from __future__ import annotations

from hse_doc_studio.api.schemas.mcp import McpCallItem, McpSettingsResponse, McpToolItem, UpdateMcpSettingsRequest
from hse_doc_studio.core.mcp.entities import McpCallRecord, McpToolGroup
from hse_doc_studio.use_cases.mcp.settings import McpSettingsChange, McpSettingsView

MCP_ENDPOINT_PATH = "/mcp"


def settings_response(view: McpSettingsView) -> McpSettingsResponse:
    s = view.settings
    return McpSettingsResponse(
        enabled=s.enabled,
        disabled_tools=sorted(s.disabled_tools),
        disabled_groups=sorted(g.value for g in s.disabled_groups),
        enabled_dangerous=sorted(s.enabled_dangerous),
        endpoint_path=MCP_ENDPOINT_PATH,
        tools=[
            McpToolItem(
                name=t.name,
                group=t.group.value,
                kind=t.kind.value,
                description=t.description,
                dangerous=t.dangerous,
                admin=t.admin,
                enabled=t.enabled,
            )
            for t in view.tools
        ],
    )


def settings_change(body: UpdateMcpSettingsRequest) -> McpSettingsChange:
    return McpSettingsChange(
        enabled=body.enabled,
        disabled_tools=frozenset(body.disabled_tools) if body.disabled_tools is not None else None,
        disabled_groups=frozenset(McpToolGroup(g) for g in body.disabled_groups)
        if body.disabled_groups is not None
        else None,
        enabled_dangerous=frozenset(body.enabled_dangerous) if body.enabled_dangerous is not None else None,
    )


def call_item(record: McpCallRecord) -> McpCallItem:
    return McpCallItem(
        at=record.at,
        tool=record.tool,
        outcome=record.outcome.value,
        duration_ms=record.duration_ms,
        actor_id=record.actor_id,
        actor_name=record.actor_name,
        project_id=record.project_id,
        error_code=record.error_code,
        client=record.client,
        arg_keys=list(record.arg_keys),
    )
