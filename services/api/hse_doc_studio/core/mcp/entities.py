"""MCP-сервер Студии: группы тулов, настройки установки и запись журнала вызовов (docs/design/mcp.md)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum

from hse_doc_studio.core.enums import ToolKind

# Области персонального токена: пользовательские тулы и админские (docs/design/mcp.md, M5 и M7).
MCP_SCOPE = "mcp"
MCP_ADMIN_SCOPE = "mcp:admin"


class McpToolGroup(StrEnum):
    account = "account"
    projects = "projects"
    files = "files"
    build = "build"
    checks = "checks"
    review = "review"
    history = "history"
    submission = "submission"
    admin = "admin"


@dataclass(frozen=True, slots=True)
class McpToolMeta:
    """Что известно о туле без его обработчика: для списка в настройках и политики включения."""

    name: str
    group: McpToolGroup
    kind: ToolKind
    # Удаление, откат истории, обмен с git-remote, админские изменения: выключены, пока их не включат поимённо.
    dangerous: bool = False
    # Есть только на сервере (ревью, админка).
    server_only: bool = False
    admin: bool = False

    @property
    def read_only(self) -> bool:
        return self.kind is ToolKind.read


# Группа админки выключена, пока её не включат явно (M7).
DEFAULT_DISABLED_GROUPS = frozenset({McpToolGroup.admin})


@dataclass(frozen=True)
class McpSettings:
    enabled: bool = False
    disabled_tools: frozenset[str] = frozenset()
    disabled_groups: frozenset[McpToolGroup] = DEFAULT_DISABLED_GROUPS
    # Опасные тулы, которые включены поимённо.
    enabled_dangerous: frozenset[str] = frozenset()

    def allows(self, meta: McpToolMeta) -> bool:
        if meta.name in self.disabled_tools or meta.group in self.disabled_groups:
            return False
        return not meta.dangerous or meta.name in self.enabled_dangerous

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "disabled_tools": sorted(self.disabled_tools),
            "disabled_groups": sorted(g.value for g in self.disabled_groups),
            "enabled_dangerous": sorted(self.enabled_dangerous),
        }

    @classmethod
    def from_dict(cls, raw: object) -> McpSettings:
        """Терпимо к мусору: неизвестные группы и не строки отбрасываются, отсутствующий ключ даёт умолчание."""
        if not isinstance(raw, Mapping):
            return cls()
        defaults = cls()
        groups = raw.get("disabled_groups")
        return cls(
            enabled=raw.get("enabled") is True,
            disabled_tools=_names(raw.get("disabled_tools")),
            disabled_groups=frozenset(_groups(groups)) if isinstance(groups, list) else defaults.disabled_groups,
            enabled_dangerous=_names(raw.get("enabled_dangerous")),
        )

    def with_changes(
        self,
        *,
        enabled: bool | None = None,
        disabled_tools: Iterable[str] | None = None,
        disabled_groups: Iterable[McpToolGroup] | None = None,
        enabled_dangerous: Iterable[str] | None = None,
    ) -> McpSettings:
        return replace(
            self,
            enabled=self.enabled if enabled is None else enabled,
            disabled_tools=self.disabled_tools if disabled_tools is None else frozenset(disabled_tools),
            disabled_groups=self.disabled_groups if disabled_groups is None else frozenset(disabled_groups),
            enabled_dangerous=self.enabled_dangerous if enabled_dangerous is None else frozenset(enabled_dangerous),
        )


def _names(raw: object) -> frozenset[str]:
    if not isinstance(raw, list):
        return frozenset()
    return frozenset(item for item in raw if isinstance(item, str) and item)


def _groups(raw: list[object]) -> Iterable[McpToolGroup]:
    for item in raw:
        if item in McpToolGroup.__members__.values():
            yield McpToolGroup(str(item))


class McpCallOutcome(StrEnum):
    ok = "ok"
    error = "error"
    denied = "denied"


@dataclass(frozen=True)
class McpCallRecord:
    """Один вызов тула. Аргументы не хранятся (там исходники), только имена ключей."""

    at: datetime
    tool: str
    outcome: McpCallOutcome
    duration_ms: int
    actor_id: str | None = None
    actor_name: str | None = None
    project_id: str | None = None
    error_code: str | None = None
    client: str | None = None
    arg_keys: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class McpCallQuery:
    tool: str | None = None
    actor_id: str | None = None
    outcome: McpCallOutcome | None = None
    limit: int = 50
