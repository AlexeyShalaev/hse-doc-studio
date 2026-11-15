from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, TypeVar

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.mcp.entities import McpCallQuery, McpCallRecord, McpSettings, McpToolMeta

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


class IMcpChangeAudit(Protocol):
    """Изменения через тулы MCP с подробностями: в облаке событие аудита, локально строка лога без значений.

    Сам вызов и так попадает в журнал (`IMcpCallJournal`), но там только имена аргументов; здесь что изменилось.
    """

    async def record(self, action: str, *, target: str | None, details: Mapping[str, object]) -> None: ...


class IMcpToolGate(Protocol):
    """Право на группу тулов сверх настроек MCP: тулы Студии шаблонов видит только тот, кому открыт её раздел
    (включён и есть право «Автор шаблонов»). Скрытый тул не попадает в `tools/list`; вызов по имени упрётся в тот же
    отказ, что у маршрутов раздела."""

    async def allows(self, actor: Actor, meta: McpToolMeta) -> bool: ...
