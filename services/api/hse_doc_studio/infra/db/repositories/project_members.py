"""Запись участников проекта: люди и группы с ролью."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.access.repositories import ProjectMemberGrant, ProjectOwnership
from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow, ProjectRow
from hse_doc_studio.infra.db.session import SessionProvider


class PostgresProjectMemberRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def get_ownership(self, project_id: UUID) -> ProjectOwnership | None:
        stmt = select(ProjectRow.owner_user_id, ProjectRow.owner_org_id).where(
            ProjectRow.id == project_id, ProjectRow.deleted_at.is_(None)
        )
        async with self._sessions.use() as session:
            row = (await session.execute(stmt)).first()
        return None if row is None else ProjectOwnership(row.owner_user_id, row.owner_org_id)

    async def set_member(self, project_id: UUID, grant: ProjectMemberGrant) -> None:
        values = {
            "role": grant.role.value,
            "persona": grant.persona,
            "can_share": grant.can_share,
            "show_sources": grant.show_sources,
            "can_edit_all": grant.can_edit_all,
        }
        insert = pg_insert(ProjectMemberRow).values(
            project_id=project_id, principal_kind=grant.principal_kind, principal_id=grant.principal_id, **values
        )
        stmt = insert.on_conflict_do_update(
            index_elements=[
                ProjectMemberRow.project_id,
                ProjectMemberRow.principal_kind,
                ProjectMemberRow.principal_id,
            ],
            set_=values,
        )
        async with self._sessions.use() as session:
            await session.execute(stmt)

    async def remove_member(self, project_id: UUID, principal_kind: str, principal_id: str) -> bool:
        stmt = (
            delete(ProjectMemberRow)
            .where(
                ProjectMemberRow.project_id == project_id,
                ProjectMemberRow.principal_kind == principal_kind,
                ProjectMemberRow.principal_id == principal_id,
            )
            .returning(ProjectMemberRow.principal_id)
        )
        async with self._sessions.use() as session:
            return (await session.execute(stmt)).first() is not None
