"""Журнал вызовов MCP для настроек: админ облака или владелец локальной Студии."""

from __future__ import annotations

from dataclasses import replace

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.mcp.entities import McpCallQuery, McpCallRecord
from hse_doc_studio.core.mcp.protocols import IMcpCallJournal
from hse_doc_studio.use_cases.mcp.settings import require_settings_owner

MAX_CALLS_PAGE = 200


class ListMcpCallsUC:
    def __init__(self, journal: IMcpCallJournal) -> None:
        self._journal = journal

    async def execute(self, actor: Actor, query: McpCallQuery) -> list[McpCallRecord]:
        require_settings_owner(actor)
        return await self._journal.recent(replace(query, limit=max(1, min(query.limit, MAX_CALLS_PAGE))))
