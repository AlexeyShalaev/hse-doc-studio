"""Журнал аудита: чтение для админа установки и стирание по сроку хранения."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta

import structlog

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.entities import AuditPage, AuditQuery
from hse_doc_studio.core.identity.protocols import IAuditLog, IAuditReader, IAuditRetention
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.use_cases.admin.users import require_admin

logger = structlog.get_logger(__name__)

MAX_AUDIT_PAGE = 200


class ListAuditUC:
    def __init__(self, reader: IAuditReader) -> None:
        self._reader = reader

    async def execute(self, actor: Actor, query: AuditQuery) -> AuditPage:
        """Страница по ключу: лишняя запись сверх `limit` только говорит, что дальше есть ещё."""
        require_admin(actor)
        limit = max(1, min(query.limit, MAX_AUDIT_PAGE))
        found = await self._reader.query(replace(query, limit=limit + 1))
        items = found[:limit]
        # Оценка только без фильтров: с ними число дорого и точно его клиенту знать не нужно.
        estimate = await self._reader.estimate_total() if not query.filtered else None
        return AuditPage(
            items=items,
            next_before_id=items[-1].entry.id if len(found) > limit else None,
            total_estimate=estimate,
        )


@dataclass(frozen=True)
class AuditPurgeReport:
    purged: int


class PurgeAuditUC:
    """Нулевой срок значит «хранить вечно». Сам прогон попадает в журнал, пока стёрто хоть что-то."""

    def __init__(
        self, retention: IAuditRetention, audit: IAuditLog, keep: timedelta, *, clock: Clock = utc_now
    ) -> None:
        self._retention = retention
        self._audit = audit
        self._keep = keep
        self._clock = clock

    async def execute(self) -> AuditPurgeReport:
        if self._keep <= timedelta(0):
            return AuditPurgeReport(0)
        purged = await self._retention.purge_before(self._clock() - self._keep)
        if purged:
            await self._audit.record(
                "audit.purged", actor_id=None, details={"count": purged, "keep_days": self._keep.days}
            )
            logger.info("audit_purged", count=purged)
        return AuditPurgeReport(purged)
