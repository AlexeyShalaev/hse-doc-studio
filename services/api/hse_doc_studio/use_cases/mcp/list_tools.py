"""Что видит клиент MCP: включённые тулы, доступные актору (админские только админу с `mcp:admin`, тулы Студии
шаблонов только тому, кому открыт её раздел)."""

from __future__ import annotations

from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.mcp.errors import McpError, McpErrorCode
from hse_doc_studio.core.mcp.protocols import IMcpSettingsStore, IMcpToolGate
from hse_doc_studio.use_cases.mcp.call_tool import visible_to
from hse_doc_studio.use_cases.mcp.catalog import McpCatalog, McpToolEntry


class ListMcpToolsUC:
    def __init__(self, catalog: McpCatalog, settings: IMcpSettingsStore, gate: IMcpToolGate | None = None) -> None:
        self._catalog = catalog
        self._settings = settings
        self._gate = gate

    async def execute(self) -> list[McpToolEntry]:
        settings = await self._settings.get()
        if not settings.enabled:
            raise McpError(McpErrorCode.mcp_disabled)
        actor = require_actor()
        visible = [e for e in self._catalog.all() if visible_to(actor, e, settings)]
        if self._gate is None:
            return visible
        allowed: dict[object, bool] = {}
        result: list[McpToolEntry] = []
        for entry in visible:
            group = entry.meta.group
            if group not in allowed:
                allowed[group] = await self._gate.allows(actor, entry.meta)
            if allowed[group]:
                result.append(entry)
        return result
