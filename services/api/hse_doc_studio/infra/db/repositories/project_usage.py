"""Учёт места проекта в Postgres: полное измерение пишет все три счётчика, запись файла сдвигает размер дерева."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.projects.usage import ProjectUsage
from hse_doc_studio.infra.db.orm.project_usage import ProjectUsageRow
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.session import SessionProvider


class PostgresProjectUsageStore:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def get(self, project_id: UUID) -> ProjectUsage | None:
        async with self._sessions.use() as session:
            row = await session.get(ProjectUsageRow, project_id)
            if row is None:
                return None
            return ProjectUsage(row.project_id, row.bytes_tree, row.bytes_git, row.bytes_s3, row.measured_at)

    async def save(self, usage: ProjectUsage) -> None:
        values = {
            "bytes_tree": usage.bytes_tree,
            "bytes_git": usage.bytes_git,
            "bytes_s3": usage.bytes_s3,
            "measured_at": usage.measured_at,
        }
        stmt = pg_insert(ProjectUsageRow).values(project_id=usage.project_id, **values)
        stmt = stmt.on_conflict_do_update(index_elements=[ProjectUsageRow.project_id], set_=values)
        async with self._sessions.use() as session:
            await session.execute(stmt)

    async def add_tree(self, project_id: UUID, delta_bytes: int, now: datetime) -> None:
        stmt = pg_insert(ProjectUsageRow).values(
            project_id=project_id, bytes_tree=max(0, delta_bytes), bytes_git=0, bytes_s3=0, measured_at=now
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[ProjectUsageRow.project_id],
            set_={"bytes_tree": func.greatest(0, ProjectUsageRow.bytes_tree + delta_bytes)},
        )
        async with self._sessions.use() as session:
            await session.execute(stmt)

    async def stale(self, older_than: datetime, limit: int) -> list[UUID]:
        stmt = (
            select(ProjectRow.id)
            .outerjoin(ProjectUsageRow, ProjectUsageRow.project_id == ProjectRow.id)
            .where(
                ProjectRow.deleted_at.is_(None),
                or_(ProjectUsageRow.measured_at.is_(None), ProjectUsageRow.measured_at < older_than),
            )
            .order_by(ProjectUsageRow.measured_at.asc().nullsfirst(), ProjectRow.id)
            .limit(limit)
        )
        async with self._sessions.use() as session:
            return list((await session.execute(stmt)).scalars().all())
