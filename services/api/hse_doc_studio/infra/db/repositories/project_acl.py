"""Членство проекта в Postgres: владелец и прямые участники."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import and_, select, update

from hse_doc_studio.core.access.entities import Actor, ActorKind, Grant, ProjectAcl, Role
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow, ProjectRow
from hse_doc_studio.infra.db.repositories.projects import USER_PRINCIPAL
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.projects.acl_flags import AclFlags, AclFlagsCache

logger = structlog.get_logger()

_ROLE_ORDER = (Role.reader, Role.reviewer, Role.editor, Role.owner)


class PostgresProjectAclRepository:
    """Один запрос на проект и актора. Организации и группы подключаются позже поверх тех же таблиц."""

    def __init__(self, sessions: SessionProvider, flags: AclFlagsCache) -> None:
        self._sessions = sessions
        self._flags = flags

    async def load_for(self, actor: Actor, project_id: UUID) -> ProjectAcl | None:
        if actor.kind is not ActorKind.user or actor.id is None:
            return None
        stmt = (
            select(
                ProjectRow.owner_user_id,
                ProjectRow.team,
                ProjectRow.shared_enabled,
                ProjectMemberRow.role,
                ProjectMemberRow.persona,
                ProjectMemberRow.show_sources,
                ProjectMemberRow.can_share,
                ProjectMemberRow.can_edit_all,
            )
            .select_from(ProjectRow)
            .outerjoin(
                ProjectMemberRow,
                and_(
                    ProjectMemberRow.project_id == ProjectRow.id,
                    ProjectMemberRow.principal_kind == USER_PRINCIPAL,
                    ProjectMemberRow.principal_id == actor.id,
                ),
            )
            .where(ProjectRow.id == project_id, ProjectRow.deleted_at.is_(None))
        )
        async with self._sessions.use() as session:
            row = (await session.execute(stmt)).first()
        if row is None:
            return None
        self._flags.put(project_id, AclFlags(team=row.team, shared_enabled=row.shared_enabled))
        grant = _grant_of(is_owner=row.owner_user_id == actor.id, row=row)
        if grant is None:
            return None
        return ProjectAcl(
            project_id=str(project_id),
            owner_id=row.owner_user_id,
            team=row.team,
            shared_enabled=row.shared_enabled,
            grants={actor.id: grant},
        )

    async def set_shared_enabled(self, project_id: UUID, enabled: bool) -> None:
        stmt = update(ProjectRow).where(ProjectRow.id == project_id).values(shared_enabled=enabled)
        async with self._sessions.use() as session:
            await session.execute(stmt)
        current = self._flags.get(project_id)
        if current is not None:
            self._flags.put(project_id, AclFlags(team=current.team, shared_enabled=enabled))


def _grant_of(*, is_owner: bool, row: Any) -> Grant | None:
    """Старшая из ролей: владелец проекта или запись участника. Непонятная роль в БД не открывает ничего."""
    member_role: Role | None = None
    if row.role is not None:
        try:
            member_role = Role(row.role)
        except ValueError:
            logger.warning("project acl: unknown role in project_members", role=row.role)
    role = Role.owner if is_owner else member_role
    if role is None:
        return None
    if member_role is not None and _ROLE_ORDER.index(member_role) > _ROLE_ORDER.index(role):
        role = member_role
    owner = role is Role.owner
    return Grant(
        role=role,
        persona_slug=row.persona,
        show_sources=bool(row.show_sources) or owner,
        can_share=bool(row.can_share) or owner,
        can_edit_all=bool(row.can_edit_all) or owner,
    )


class RequestAclCache:
    """Кэш одного запроса: гард и сценарии спрашивают права одного проекта несколько раз."""

    def __init__(self, inner: IProjectAclRepository) -> None:
        self._inner = inner
        self._loaded: dict[tuple[str | None, UUID], ProjectAcl | None] = {}

    async def load_for(self, actor: Actor, project_id: UUID) -> ProjectAcl | None:
        key = (actor.key, project_id)
        if key not in self._loaded:
            self._loaded[key] = await self._inner.load_for(actor, project_id)
        return self._loaded[key]

    async def set_shared_enabled(self, project_id: UUID, enabled: bool) -> None:
        await self._inner.set_shared_enabled(project_id, enabled)
        self._loaded = {k: v for k, v in self._loaded.items() if k[1] != project_id}
