"""Студия шаблонов в админке установки: включение раздела и право «Автор шаблонов» людям и группам (сервер).

Каждое изменение пишется в журнал аудита в той же транзакции. Право в Студии разрешает только готовить предложения:
решение о слиянии принимает хостинг git (docs/design/template-studio.md, 3.3).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.pack_studio.entities import GrantSubjectKind, PackStudioGrant, SectionState
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.protocols import IPackStudioGrantRepository, IPackStudioSectionStore
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.pack_studio.access import PackStudioAccess

AUDIT_SECTION = "pack_studio.section_update"
AUDIT_GRANT = "pack_studio.grant_add"
AUDIT_REVOKE = "pack_studio.grant_remove"


@dataclass(frozen=True)
class PackStudioAdminView:
    section: SectionState
    grants: tuple[PackStudioGrant, ...]


class PackStudioAdminUC:
    def __init__(
        self,
        access: PackStudioAccess,
        store: IPackStudioSectionStore,
        grants: IPackStudioGrantRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> None:
        self._access = access
        self._store = store
        self._grants = grants
        self._audit = audit
        self._uow = uow

    async def view(self, actor: Actor) -> PackStudioAdminView:
        require_admin(actor)
        return PackStudioAdminView(section=await self._access.section(), grants=tuple(await self._grants.list()))

    async def set_enabled(self, actor: Actor, enabled: bool) -> PackStudioAdminView:
        admin_id = require_admin(actor)
        if (await self._access.section()).locked:
            raise PackStudioError(PackStudioErrorCode.section_locked)
        async with self._uow.begin():
            await self._store.set(enabled)
            await self._audit.record(AUDIT_SECTION, actor_id=admin_id, details={"enabled": enabled})
        return await self.view(actor)

    async def grant(self, actor: Actor, kind: GrantSubjectKind, subject_id: str) -> PackStudioGrant:
        admin_id = require_admin(actor)
        if not await self._grants.subject_exists(kind, subject_id):
            raise PackStudioError(PackStudioErrorCode.grant_subject_not_found)
        grant = PackStudioGrant(
            id=uuid4(), subject=kind, subject_id=subject_id, created_at=datetime.now(UTC), granted_by=admin_id
        )
        async with self._uow.begin():
            if not await self._grants.add(grant):
                raise PackStudioError(PackStudioErrorCode.grant_exists)
            listed = next((g for g in await self._grants.list() if g.id == grant.id), grant)
            await self._audit.record(AUDIT_GRANT, actor_id=admin_id, target=subject_id, details=_audit_details(listed))
        return listed

    async def revoke(self, actor: Actor, grant_id: UUID) -> None:
        admin_id = require_admin(actor)
        async with self._uow.begin():
            removed = await self._grants.remove(grant_id)
            if removed is None:
                raise PackStudioError(PackStudioErrorCode.grant_not_found)
            await self._audit.record(
                AUDIT_REVOKE,
                actor_id=admin_id,
                target=removed.subject_id,
                details=_audit_details(removed),
            )


def _audit_details(grant: PackStudioGrant) -> dict[str, object]:
    """Подпись цели в журнале: имя человека или название группы (`name`), вид субъекта и id права."""
    details: dict[str, object] = {"subject": grant.subject.value, "grant_id": str(grant.id)}
    if grant.name:
        details["name"] = grant.name if grant.org_name is None else f"{grant.org_name}: {grant.name}"
    return details
