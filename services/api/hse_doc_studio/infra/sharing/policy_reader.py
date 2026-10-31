"""Политика ссылок проекта: ключи установки (`instance_settings`) и блок `sharing` организации-владельца."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import select

from hse_doc_studio.core.access.sharing_policy import (
    InstanceSharing,
    SharingEnvOverrides,
    SharingPolicy,
    effective_instance_sharing,
    effective_policy,
    parse_org_sharing,
)
from hse_doc_studio.core.identity.protocols import IInstanceSettingsRepository
from hse_doc_studio.infra.db.orm.orgs import OrgRow
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.session import SessionProvider


class PostgresSharingPolicyReader:
    """Читает на каждый вызов: ужесточение политики действует со следующего запроса без кэша."""

    def __init__(
        self, sessions: SessionProvider, settings: IInstanceSettingsRepository, env: SharingEnvOverrides
    ) -> None:
        self._sessions = sessions
        self._settings = settings
        self._env = env

    async def instance_sharing(self) -> InstanceSharing:
        return effective_instance_sharing(await self._settings.get_all(), self._env)

    async def instance(self) -> SharingPolicy:
        return effective_policy(await self.instance_sharing(), None)

    async def for_project(self, project_id: UUID) -> SharingPolicy:
        stmt = (
            select(ProjectRow.owner_org_id, OrgRow.policies)
            .select_from(ProjectRow)
            .outerjoin(OrgRow, OrgRow.id == ProjectRow.owner_org_id)
            .where(ProjectRow.id == project_id)
        )
        async with self._sessions.use() as db:
            row = (await db.execute(stmt)).first()
        return await self.for_owner(row.owner_org_id if row else None, row.policies if row else None)

    async def for_owner(self, org_id: str | None, policies: Mapping[str, Any] | None) -> SharingPolicy:
        instance = await self.instance_sharing()
        return effective_policy(instance, parse_org_sharing(policies) if org_id is not None else None)
