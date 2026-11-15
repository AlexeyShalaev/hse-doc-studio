"""Журнал аудита установки для каталогов паков (порт ICatalogAudit): запись в своей транзакции."""

from __future__ import annotations

from collections.abc import Mapping

from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.uow import IUnitOfWork


class UowCatalogAudit:
    def __init__(self, audit: IAuditLog, uow: IUnitOfWork) -> None:
        self._audit = audit
        self._uow = uow

    async def record(
        self, action: str, *, actor_id: str | None, target: str | None, details: Mapping[str, object]
    ) -> None:
        async with self._uow.begin():
            await self._audit.record(action, actor_id=actor_id, target=target, details=details)
