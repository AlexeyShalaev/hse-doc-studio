"""Репозиторий участников с проверкой квоты: новый участник занимает слот, смена роли существующего нет."""

from __future__ import annotations

from uuid import UUID

from hse_doc_studio.core.access.repositories import IProjectMemberRepository, ProjectMemberGrant, ProjectOwnership
from hse_doc_studio.core.quotas.protocols import IQuotaGate


class QuotaGuardedMemberRepository:
    def __init__(self, inner: IProjectMemberRepository, gate: IQuotaGate) -> None:
        self._inner = inner
        self._gate = gate

    async def get_ownership(self, project_id: UUID) -> ProjectOwnership | None:
        return await self._inner.get_ownership(project_id)

    async def set_member(self, project_id: UUID, grant: ProjectMemberGrant) -> None:
        await self._gate.ensure_member_slot(project_id, grant.principal_kind, grant.principal_id)
        await self._inner.set_member(project_id, grant)

    async def remove_member(self, project_id: UUID, principal_kind: str, principal_id: str) -> bool:
        return await self._inner.remove_member(project_id, principal_kind, principal_id)
