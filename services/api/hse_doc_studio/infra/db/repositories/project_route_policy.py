"""Политика сборок проекта для маршрута задач: владелец, `build_runners` и удаление из каталога проектов."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update

from hse_doc_studio.core.jobs.routing import ProjectBuildRunners, ProjectRouteInfo
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.session import SessionProvider


class SqlProjectRoutePolicyRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def get(self, project_id: UUID) -> ProjectRouteInfo | None:
        stmt = select(
            ProjectRow.owner_user_id, ProjectRow.owner_org_id, ProjectRow.build_runners, ProjectRow.deleted_at
        ).where(ProjectRow.id == project_id)
        async with self._sessions.use() as db:
            row = (await db.execute(stmt)).one_or_none()
        if row is None:
            return None
        return ProjectRouteInfo(
            project_id=project_id,
            owner_user_id=row.owner_user_id,
            owner_org_id=row.owner_org_id,
            build_runners=ProjectBuildRunners(row.build_runners),
            deleted=row.deleted_at is not None,
        )

    async def set_build_runners(self, project_id: UUID, policy: ProjectBuildRunners) -> bool:
        stmt = update(ProjectRow).where(ProjectRow.id == project_id).values(build_runners=policy.value)
        async with self._sessions.use() as db:
            return (await db.execute(stmt)).rowcount > 0  # type: ignore[attr-defined]
