"""Локальная Студия: настройки MCP в config.json (ключ `mcp`), журнал вызовов в памяти процесса."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping

import structlog

from hse_doc_studio.core.mcp.entities import McpCallQuery, McpCallRecord, McpSettings
from hse_doc_studio.core.repositories import ISettingsRepository

logger = structlog.get_logger(__name__)

SETTINGS_KEY = "mcp"
JOURNAL_SIZE = 500


class LocalMcpSettingsStore:
    def __init__(self, settings: ISettingsRepository) -> None:
        self._settings = settings

    async def get(self) -> McpSettings:
        return McpSettings.from_dict((await self._settings.get()).get(SETTINGS_KEY))

    async def save(self, settings: McpSettings) -> None:
        current = dict(await self._settings.get())
        current[SETTINGS_KEY] = settings.to_dict()
        await self._settings.save(current)


class MemoryMcpCallJournal:
    """Последние вызовы одной локальной Студии; после перезапуска журнал пуст."""

    def __init__(self, size: int = JOURNAL_SIZE) -> None:
        self._records: deque[McpCallRecord] = deque(maxlen=size)

    async def record(self, record: McpCallRecord) -> None:
        self._records.append(record)

    async def recent(self, query: McpCallQuery) -> list[McpCallRecord]:
        found = [
            r
            for r in reversed(self._records)
            if (query.tool is None or r.tool == query.tool)
            and (query.actor_id is None or r.actor_id == query.actor_id)
            and (query.outcome is None or r.outcome is query.outcome)
        ]
        return found[: query.limit]


class LogMcpChangeAudit:
    """Локально аудита нет: вызов уже в журнале, а здесь строка лога с именами полей, без значений (там ФИО)."""

    async def record(self, action: str, *, target: str | None, details: Mapping[str, object]) -> None:
        fields = details.get("fields")
        logger.info("mcp_change", action=action, target=target, fields=fields if isinstance(fields, list) else None)
