"""Настройки MCP: общий переключатель, группы и тулы, опасные тулы поимённо (docs/design/mcp.md, раздел 4).

В облаке меняет только админ установки; локально единственный актор и есть владелец установки.
"""

from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.mcp.entities import McpSettings, McpToolGroup
from hse_doc_studio.core.mcp.protocols import IMcpSettingsStore
from hse_doc_studio.use_cases.mcp.catalog import McpCatalog

# Событие аудита облака при смене настроек; пишет его серверное хранилище (infra/mcp/server.py).
SETTINGS_AUDIT_ACTION = "settings.mcp_update"


@dataclass(frozen=True)
class McpToolView:
    name: str
    group: McpToolGroup
    kind: ToolKind
    description: str
    dangerous: bool
    admin: bool
    enabled: bool


@dataclass(frozen=True)
class McpSettingsView:
    settings: McpSettings
    tools: list[McpToolView]


@dataclass(frozen=True)
class McpSettingsChange:
    enabled: bool | None = None
    disabled_tools: frozenset[str] | None = None
    disabled_groups: frozenset[McpToolGroup] | None = None
    enabled_dangerous: frozenset[str] | None = None


def require_settings_owner(actor: Actor) -> None:
    if not actor.is_local and not actor.is_instance_admin:
        raise IdentityError(IdentityErrorCode.not_found)


def settings_view(catalog: McpCatalog, settings: McpSettings) -> McpSettingsView:
    return McpSettingsView(
        settings=settings,
        tools=[
            McpToolView(
                name=e.meta.name,
                group=e.meta.group,
                kind=e.meta.kind,
                description=e.spec.description,
                dangerous=e.meta.dangerous,
                admin=e.meta.admin,
                enabled=settings.allows(e.meta),
            )
            for e in catalog.all()
        ],
    )


class GetMcpSettingsUC:
    def __init__(self, catalog: McpCatalog, store: IMcpSettingsStore) -> None:
        self._catalog = catalog
        self._store = store

    async def execute(self, actor: Actor) -> McpSettingsView:
        require_settings_owner(actor)
        return settings_view(self._catalog, await self._store.get())


class UpdateMcpSettingsUC:
    def __init__(self, catalog: McpCatalog, store: IMcpSettingsStore) -> None:
        self._catalog = catalog
        self._store = store

    async def execute(self, actor: Actor, change: McpSettingsChange) -> McpSettingsView:
        require_settings_owner(actor)
        known = {e.meta.name for e in self._catalog.all()}
        dangerous = {e.meta.name for e in self._catalog.all() if e.meta.dangerous}
        for names, allowed in ((change.disabled_tools, known), (change.enabled_dangerous, dangerous)):
            unknown = sorted((names or frozenset()) - allowed)
            if unknown:
                raise ValueError(f"unknown tools: {', '.join(unknown)}")
        current = await self._store.get()
        updated = current.with_changes(
            enabled=change.enabled,
            disabled_tools=change.disabled_tools,
            disabled_groups=change.disabled_groups,
            enabled_dangerous=change.enabled_dangerous,
        )
        if updated != current:
            await self._store.save(updated)
        return settings_view(self._catalog, updated)
