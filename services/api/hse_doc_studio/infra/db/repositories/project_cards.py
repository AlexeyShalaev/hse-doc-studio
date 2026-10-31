"""Проект для приглашений и передачи владения: имя, владелец, кто решает доступ, смена владельца."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update

from hse_doc_studio.core.invitations.entities import OwnerKind, ProjectCard
from hse_doc_studio.core.orgs.entities import OrgRole
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.orm.orgs import OrgMemberRow, OrgRow
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.repositories.project_directory import PostgresProjectAccessDirectory
from hse_doc_studio.infra.db.session import SessionProvider

_MANAGERS = (OrgRole.owner.value, OrgRole.admin.value)


def _card_select() -> Any:
    return (
        select(
            ProjectRow.id,
            ProjectRow.name,
            ProjectRow.owner_user_id,
            ProjectRow.owner_org_id,
            ProjectRow.nda,
            func.coalesce(OrgRow.name, UserRow.name, "").label("owner_name"),
        )
        .outerjoin(UserRow, UserRow.id == ProjectRow.owner_user_id)
        .outerjoin(OrgRow, OrgRow.id == ProjectRow.owner_org_id)
        .where(ProjectRow.deleted_at.is_(None))
    )


def _card(row: Any) -> ProjectCard:
    return ProjectCard(
        id=row.id,
        name=row.name,
        owner_user_id=row.owner_user_id,
        owner_org_id=row.owner_org_id,
        owner_name=row.owner_name,
        nda=bool(row.nda),
    )


class PostgresProjectCards:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions
        self._directory = PostgresProjectAccessDirectory(sessions)

    async def card(self, project_id: UUID) -> ProjectCard | None:
        async with self._sessions.use() as session:
            row = (await session.execute(_card_select().where(ProjectRow.id == project_id))).first()
        return None if row is None else _card(row)

    async def lock_card(self, project_id: UUID) -> ProjectCard | None:
        async with self._sessions.use() as session:
            locked = (
                await session.execute(
                    select(ProjectRow.id)
                    .where(ProjectRow.id == project_id, ProjectRow.deleted_at.is_(None))
                    .with_for_update()
                )
            ).first()
            if locked is None:
                return None
            row = (await session.execute(_card_select().where(ProjectRow.id == project_id))).first()
        return None if row is None else _card(row)

    async def set_owner(self, project_id: UUID, kind: OwnerKind, owner_id: str) -> None:
        values = (
            {"owner_user_id": owner_id, "owner_org_id": None}
            if kind == "user"
            else {"owner_user_id": None, "owner_org_id": owner_id}
        )
        async with self._sessions.use() as session:
            await session.execute(
                update(ProjectRow)
                .where(ProjectRow.id == project_id)
                .values(**values, build_runners="shared", updated_at=func.now())
            )

    async def managers(self, project_id: UUID) -> list[str]:
        async with self._sessions.use() as session:
            project = (
                await session.execute(
                    select(ProjectRow.owner_user_id, ProjectRow.owner_org_id).where(ProjectRow.id == project_id)
                )
            ).first()
            if project is None:
                return []
            if project.owner_user_id is not None:
                return [project.owner_user_id]
            rows = await session.execute(
                select(OrgMemberRow.user_id)
                .where(OrgMemberRow.org_id == project.owner_org_id, OrgMemberRow.role.in_(_MANAGERS))
                .order_by(OrgMemberRow.user_id)
            )
            return [r for (r,) in rows.all()]

    async def is_transfer_candidate(self, project_id: UUID, actor_id: str, kind: OwnerKind, target_id: str) -> bool:
        return await self._directory.is_transfer_candidate(project_id, actor_id, kind, target_id)
