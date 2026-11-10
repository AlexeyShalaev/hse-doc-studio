"""Аудит действий с подписями: на сервере журнал аудита от имени актора, локально строка лога."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

import structlog

from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.signing_route.audit import current_signing_route
from hse_doc_studio.core.uow import IUnitOfWork

logger = structlog.get_logger()


class LogSignatureAudit:
    async def record(self, action: str, *, project_id: UUID | None, details: Mapping[str, object]) -> None:
        logger.info(
            "signature_audit", action=action, project_id=str(project_id) if project_id else None, **dict(details)
        )


class ServerSignatureAudit:
    def __init__(self, audit: IAuditLog, uow: IUnitOfWork) -> None:
        self._audit = audit
        self._uow = uow

    async def record(self, action: str, *, project_id: UUID | None, details: Mapping[str, object]) -> None:
        actor = current_actor()
        target = str(project_id) if project_id is not None else None
        body = {"project_id": target, **dict(details)} if target else dict(details)
        # Действие сделано маршрутом подписания или его участником в свою очередь (signing-route.md, 6.7).
        route_id = current_signing_route()
        if route_id is not None:
            body.setdefault("route_id", str(route_id))
        async with self._uow.begin():
            await self._audit.record(
                action, actor_id=actor.id if actor is not None else None, target=target, details=body
            )
