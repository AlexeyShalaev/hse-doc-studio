"""Postgres: счётчики расхода по периодам и расход, который считается по таблицам проектов."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.jobs.quotas import QuotaOwnerKind
from hse_doc_studio.core.quotas.kinds import QuotaKind
from hse_doc_studio.core.quotas.protocols import CounterTotal, ProjectOwner
from hse_doc_studio.infra.db.orm.project_usage import ProjectUsageRow
from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow, ProjectRow
from hse_doc_studio.infra.db.orm.quotas import UsageCounterRow
from hse_doc_studio.infra.db.session import SessionProvider


class SqlUsageCounters:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def get(self, owner_kind: QuotaOwnerKind, owner_id: str, kind: QuotaKind, start: date) -> int:
        stmt = select(UsageCounterRow.used).where(
            UsageCounterRow.owner_kind == owner_kind.value,
            UsageCounterRow.owner_id == owner_id,
            UsageCounterRow.resource == kind.value,
            UsageCounterRow.period_start == start,
        )
        async with self._sessions.use() as session:
            return int((await session.execute(stmt)).scalar_one_or_none() or 0)

    async def add(self, owner_kind: QuotaOwnerKind, owner_id: str, kind: QuotaKind, start: date, amount: int) -> int:
        stmt = pg_insert(UsageCounterRow).values(
            owner_kind=owner_kind.value, owner_id=owner_id, resource=kind.value, period_start=start, used=amount
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                UsageCounterRow.owner_kind,
                UsageCounterRow.owner_id,
                UsageCounterRow.resource,
                UsageCounterRow.period_start,
            ],
            set_={"used": UsageCounterRow.used + amount, "updated_at": func.now()},
        ).returning(UsageCounterRow.used)
        async with self._sessions.use() as session:
            return int((await session.execute(stmt)).scalar_one())

    async def reset(self, owner_kind: QuotaOwnerKind, owner_id: str, kind: QuotaKind, start: date) -> bool:
        stmt = delete(UsageCounterRow).where(
            UsageCounterRow.owner_kind == owner_kind.value,
            UsageCounterRow.owner_id == owner_id,
            UsageCounterRow.resource == kind.value,
            UsageCounterRow.period_start == start,
        )
        async with self._sessions.use() as session:
            return bool((await session.execute(stmt)).rowcount)  # type: ignore[attr-defined]

    async def total(self, kind: QuotaKind, start: date) -> int:
        # Итог установки считаем по людям: организация дублирует расход своих участников.
        stmt = select(func.coalesce(func.sum(UsageCounterRow.used), 0)).where(
            UsageCounterRow.owner_kind == QuotaOwnerKind.user.value,
            UsageCounterRow.resource == kind.value,
            UsageCounterRow.period_start == start,
        )
        async with self._sessions.use() as session:
            return int((await session.execute(stmt)).scalar_one())

    async def top(self, kind: QuotaKind, start: date, owner_kind: QuotaOwnerKind, limit: int) -> Sequence[CounterTotal]:
        stmt = (
            select(UsageCounterRow.owner_id, UsageCounterRow.used)
            .where(
                UsageCounterRow.owner_kind == owner_kind.value,
                UsageCounterRow.resource == kind.value,
                UsageCounterRow.period_start == start,
            )
            .order_by(UsageCounterRow.used.desc(), UsageCounterRow.owner_id)
            .limit(limit)
        )
        async with self._sessions.use() as session:
            return tuple(CounterTotal(owner_kind, oid, int(used)) for oid, used in (await session.execute(stmt)).all())

    async def prune(self, before: date) -> int:
        async with self._sessions.use() as session:
            result = await session.execute(delete(UsageCounterRow).where(UsageCounterRow.period_start < before))
            return int(result.rowcount or 0)  # type: ignore[attr-defined]


def _owner_filter(owner_kind: QuotaOwnerKind, owner_id: str):  # type: ignore[no-untyped-def]  # noqa: ANN202
    if owner_kind is QuotaOwnerKind.org:
        return ProjectRow.owner_org_id == owner_id
    return (ProjectRow.owner_user_id == owner_id) & ProjectRow.owner_org_id.is_(None)


class SqlOwnerFootprint:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def project_owner(self, project_id: UUID) -> ProjectOwner | None:
        stmt = select(ProjectRow.owner_user_id, ProjectRow.owner_org_id).where(
            ProjectRow.id == project_id, ProjectRow.deleted_at.is_(None)
        )
        async with self._sessions.use() as session:
            row = (await session.execute(stmt)).one_or_none()
        return ProjectOwner(project_id, row[0], row[1]) if row is not None else None

    async def storage_bytes(self, owner_kind: QuotaOwnerKind, owner_id: str) -> int:
        stmt = (
            select(
                func.coalesce(
                    func.sum(ProjectUsageRow.bytes_tree + ProjectUsageRow.bytes_git + ProjectUsageRow.bytes_s3), 0
                )
            )
            .join(ProjectRow, ProjectRow.id == ProjectUsageRow.project_id)
            .where(ProjectRow.deleted_at.is_(None), _owner_filter(owner_kind, owner_id))
        )
        async with self._sessions.use() as session:
            return int((await session.execute(stmt)).scalar_one())

    async def storage_total(self) -> int:
        stmt = (
            select(
                func.coalesce(
                    func.sum(ProjectUsageRow.bytes_tree + ProjectUsageRow.bytes_git + ProjectUsageRow.bytes_s3), 0
                )
            )
            .join(ProjectRow, ProjectRow.id == ProjectUsageRow.project_id)
            .where(ProjectRow.deleted_at.is_(None))
        )
        async with self._sessions.use() as session:
            return int((await session.execute(stmt)).scalar_one())

    async def member_count(self, project_id: UUID) -> int:
        stmt = select(func.count()).select_from(ProjectMemberRow).where(ProjectMemberRow.project_id == project_id)
        async with self._sessions.use() as session:
            return int((await session.execute(stmt)).scalar_one())

    async def has_member(self, project_id: UUID, principal_kind: str, principal_id: str) -> bool:
        stmt = select(ProjectMemberRow.project_id).where(
            ProjectMemberRow.project_id == project_id,
            ProjectMemberRow.principal_kind == principal_kind,
            ProjectMemberRow.principal_id == principal_id,
        )
        async with self._sessions.use() as session:
            return (await session.execute(stmt)).first() is not None

    async def max_members(self, owner_kind: QuotaOwnerKind, owner_id: str) -> int:
        counts = (
            select(func.count().label("n"))
            .select_from(ProjectMemberRow)
            .join(ProjectRow, ProjectRow.id == ProjectMemberRow.project_id)
            .where(ProjectRow.deleted_at.is_(None), _owner_filter(owner_kind, owner_id))
            .group_by(ProjectMemberRow.project_id)
            .subquery()
        )
        async with self._sessions.use() as session:
            return int((await session.execute(select(func.coalesce(func.max(counts.c.n), 0)))).scalar_one())
