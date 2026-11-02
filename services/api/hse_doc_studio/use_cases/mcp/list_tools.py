"""Что видит клиент MCP: включённые тулы, доступные актору (админские только админу с `mcp:admin`)."""

from __future__ import annotations

from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.mcp.errors import McpError, McpErrorCode
from hse_doc_studio.core.mcp.protocols import IMcpSettingsStore
from hse_doc_studio.use_cases.mcp.call_tool import visible_to
from hse_doc_studio.use_cases.mcp.catalog import McpCatalog, McpToolEntry


class ListMcpToolsUC:
    def __init__(self, catalog: McpCatalog, settings: IMcpSettingsStore) -> None:
        self._catalog = catalog
        self._settings = settings

    async def execute(self) -> list[McpToolEntry]:
        settings = await self._settings.get()
        if not settings.enabled:
            raise McpError(McpErrorCode.mcp_disabled)
        actor = require_actor()
        return [e for e in self._catalog.all() if visible_to(actor, e, settings)]
