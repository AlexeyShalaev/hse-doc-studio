from __future__ import annotations

from typing import Protocol, TypeVar

from hse_doc_studio.core.mcp.entities import McpCallQuery, McpCallRecord, McpSettings

T = TypeVar("T")


class IMcpSettingsStore(Protocol):
    """Настройки MCP: в облаке на установку (`instance_settings`), локально в config.json."""

    async def get(self) -> McpSettings: ...
    async def save(self, settings: McpSettings) -> None: ...


class IMcpCallJournal(Protocol):
    """Журнал вызовов: в облаке события аудита `mcp.call`, локально кольцевой буфер в памяти."""

    async def record(self, record: McpCallRecord) -> None: ...
    async def recent(self, query: McpCallQuery) -> list[McpCallRecord]: ...


class IDependencyResolver(Protocol):
    """Достаёт сценарий по типу из контейнера запроса.

    Тулы MCP берут сценарии лениво: часть из них есть только на сервере (ревью, админка), и каталог собирается
    в любом режиме, а сценарий понадобится только при вызове.
    """

    async def get(self, dependency_type: type[T], component: str | None = ...) -> T: ...
