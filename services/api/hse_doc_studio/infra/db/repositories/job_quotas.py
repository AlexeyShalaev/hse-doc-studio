"""Postgres: переопределения квот и организация-владелец проекта для очереди."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.jobs.quotas import QuotaOverride, QuotaOwnerKind, QuotaResource, org_key
from hse_doc_studio.infra.db.orm.jobs import QuotaRow
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.session import SessionProvider

NO_PERIOD = "none"


class SqlQuotaOverrideRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def list_all(self) -> Sequence[QuotaOverride]:
        async with self._sessions.use() as session:
            rows = (await session.execute(select(QuotaRow).where(QuotaRow.period == NO_PERIOD))).scalars()
            return tuple(
                QuotaOverride(QuotaOwnerKind(row.owner_kind), row.owner_id, QuotaResource(row.resource), row.hard_limit)
                for row in rows
                if row.owner_kind in QuotaOwnerKind and row.resource in QuotaResource
            )

    async def set(self, override: QuotaOverride) -> None:
        values = {
            "owner_kind": override.owner_kind.value,
            "owner_id": override.owner_id,
            "resource": override.resource.value,
            "period": NO_PERIOD,
            "hard_limit": override.hard_limit,
        }
        async with self._sessions.use() as session:
            await session.execute(
                pg_insert(QuotaRow)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=[QuotaRow.owner_kind, QuotaRow.owner_id, QuotaRow.resource, QuotaRow.period],
                    set_={"hard_limit": override.hard_limit},
                )
            )

    async def delete(self, owner_kind: QuotaOwnerKind, owner_id: str, resource: QuotaResource) -> None:
        async with self._sessions.use() as session:
            await session.execute(
                delete(QuotaRow).where(
                    QuotaRow.owner_kind == owner_kind.value,
                    QuotaRow.owner_id == owner_id,
                    QuotaRow.resource == resource.value,
                    QuotaRow.period == NO_PERIOD,
                )
            )


class SqlProjectOrgReader:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def org_of(self, project_id: UUID) -> UUID | None:
        async with self._sessions.use() as session:
            owner_org = (
                await session.execute(select(ProjectRow.owner_org_id).where(ProjectRow.id == project_id))
            ).scalar_one_or_none()
        return org_key(owner_org) if owner_org else None
