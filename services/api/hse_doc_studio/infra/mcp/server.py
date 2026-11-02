"""Облако: настройки MCP на установку (`instance_settings`, ключ `mcp.config`), журнал вызовов в аудите."""

from __future__ import annotations

from collections.abc import Mapping

from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.identity.entities import AuditQuery, AuditView
from hse_doc_studio.core.identity.protocols import IAuditLog, IAuditReader, IInstanceSettingsRepository
from hse_doc_studio.core.mcp.entities import McpCallOutcome, McpCallQuery, McpCallRecord, McpSettings
from hse_doc_studio.core.settings_scope import SOURCE_ADMIN
from hse_doc_studio.core.uow import IUnitOfWork

SETTINGS_KEY = "mcp.config"
CALL_ACTION = "mcp.call"
SETTINGS_ACTION = "settings.mcp_update"
# Фильтр по исходу и тулу идёт после чтения: берём с запасом.
_OVERFETCH = 4


class ServerMcpSettingsStore:
    def __init__(self, repo: IInstanceSettingsRepository, audit: IAuditLog, uow: IUnitOfWork) -> None:
        self._repo = repo
        self._audit = audit
        self._uow = uow

    async def get(self) -> McpSettings:
        return McpSettings.from_dict((await self._repo.get_all()).get(SETTINGS_KEY))

    async def save(self, settings: McpSettings) -> None:
        before = await self.get()
        actor = current_actor()
        async with self._uow.begin():
            await self._repo.set(SETTINGS_KEY, settings.to_dict(), source=SOURCE_ADMIN)
            await self._audit.record(
                SETTINGS_ACTION,
                actor_id=actor.id if actor is not None else None,
                details={"before": before.to_dict(), "after": settings.to_dict()},
            )


class AuditMcpCallJournal:
    def __init__(self, audit: IAuditLog, reader: IAuditReader, uow: IUnitOfWork) -> None:
        self._audit = audit
        self._reader = reader
        self._uow = uow

    async def record(self, record: McpCallRecord) -> None:
        async with self._uow.begin():
            await self._audit.record(
                CALL_ACTION,
                actor_id=record.actor_id,
                target=record.tool,
                details={
                    "outcome": record.outcome.value,
                    "duration_ms": record.duration_ms,
                    "project_id": record.project_id,
                    "error_code": record.error_code,
                    "client": record.client,
                    "arg_keys": list(record.arg_keys),
                },
            )

    async def recent(self, query: McpCallQuery) -> list[McpCallRecord]:
        views = await self._reader.query(
            AuditQuery(
                actor_id=query.actor_id,
                actions=(CALL_ACTION,),
                target=query.tool,
                limit=query.limit * (_OVERFETCH if query.outcome else 1),
            )
        )
        records = [_record(v) for v in views]
        if query.outcome is not None:
            records = [r for r in records if r.outcome is query.outcome]
        return records[: query.limit]


def _record(view: AuditView) -> McpCallRecord:
    details: Mapping[str, object] = view.entry.details
    raw_outcome = details.get("outcome")
    outcome = McpCallOutcome(raw_outcome) if raw_outcome in {o.value for o in McpCallOutcome} else McpCallOutcome.ok
    duration = details.get("duration_ms")
    keys = details.get("arg_keys")
    return McpCallRecord(
        at=view.entry.at,
        tool=view.entry.target or "",
        outcome=outcome,
        duration_ms=duration if isinstance(duration, int) else 0,
        actor_id=view.entry.actor_id,
        actor_name=view.actor.name if view.actor is not None else None,
        project_id=_text(details.get("project_id")),
        error_code=_text(details.get("error_code")),
        client=_text(details.get("client")),
        arg_keys=tuple(str(k) for k in keys) if isinstance(keys, list) else (),
    )


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
