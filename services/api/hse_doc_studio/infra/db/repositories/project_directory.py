"""Панель «Доступ» проекта: кто имеет доступ и кого можно добавить. Чужих людей по всей установке не перебрать."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, func, or_, select

from hse_doc_studio.core.access.entities import Role
from hse_doc_studio.core.access.repositories import ProjectAccessRow, ProjectCandidate
from hse_doc_studio.core.identity.entities import UserStatus
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.orm.orgs import GroupRow, OrgMemberRow, OrgRow
from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow, ProjectRow
from hse_doc_studio.infra.db.repositories.projects import GROUP_PRINCIPAL, USER_PRINCIPAL
from hse_doc_studio.infra.db.session import SessionProvider


def _like(query: str) -> str:
    escaped = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _scope_orgs(owner_org_id: str | None, actor_id: str) -> Select[Any]:
    """Организации, из которых берут группы и людей: у проекта организации только она, иначе организации смотрящего."""
    if owner_org_id is not None:
        return select(OrgRow.id).where(OrgRow.id == owner_org_id)
    return select(OrgMemberRow.org_id).where(OrgMemberRow.user_id == actor_id)


def _visible_people(owner_org_id: str | None, actor_id: str, scope_orgs: Select[Any]) -> ColumnElement[bool]:
    """Люди, которых смотрящий вправе видеть: общая организация и, для личного проекта, уже открытые им проекты."""
    visible: list[ColumnElement[bool]] = [
        UserRow.id.in_(select(OrgMemberRow.user_id).where(OrgMemberRow.org_id.in_(scope_orgs)))
    ]
    if owner_org_id is None:
        # Люди, которым смотрящий уже открывал свои проекты, тоже известны ему.
        known_from_projects = (
            select(ProjectMemberRow.principal_id)
            .join(ProjectRow, ProjectRow.id == ProjectMemberRow.project_id)
            .where(
                ProjectRow.owner_user_id == actor_id,
                ProjectRow.deleted_at.is_(None),
                ProjectMemberRow.principal_kind == USER_PRINCIPAL,
            )
        )
        visible.append(UserRow.id.in_(known_from_projects))
    return or_(*visible)


def _role_or_none(raw: str) -> Role | None:
    try:
        return Role(raw)
    except ValueError:
        return None


class PostgresProjectAccessDirectory:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def list_access(self, project_id: UUID) -> list[ProjectAccessRow]:
        async with self._sessions.use() as session:
            project = (
                await session.execute(
                    select(ProjectRow.owner_user_id, ProjectRow.owner_org_id).where(
                        ProjectRow.id == project_id, ProjectRow.deleted_at.is_(None)
                    )
                )
            ).first()
            if project is None:
                return []
            head: list[ProjectAccessRow] = []
            if project.owner_user_id is not None:
                owner = (
                    await session.execute(
                        select(UserRow.name, UserRow.email).where(UserRow.id == project.owner_user_id)
                    )
                ).first()
                if owner is not None:
                    head.append(
                        ProjectAccessRow("user", project.owner_user_id, owner.name, owner.email, Role.owner, True)
                    )
            if project.owner_org_id is not None:
                org_name = (
                    await session.execute(select(OrgRow.name).where(OrgRow.id == project.owner_org_id))
                ).scalar_one_or_none()
                if org_name is not None:
                    head.append(ProjectAccessRow("org", project.owner_org_id, org_name, None, Role.reader, True))
            users = (
                await session.execute(
                    select(ProjectMemberRow.principal_id, ProjectMemberRow.role, UserRow.name, UserRow.email)
                    .join(UserRow, UserRow.id == ProjectMemberRow.principal_id)
                    .where(
                        ProjectMemberRow.project_id == project_id,
                        ProjectMemberRow.principal_kind == USER_PRINCIPAL,
                        ProjectMemberRow.principal_id != (project.owner_user_id or ""),
                    )
                )
            ).all()
            groups = (
                await session.execute(
                    select(ProjectMemberRow.principal_id, ProjectMemberRow.role, GroupRow.name, OrgRow.name)
                    .join(GroupRow, GroupRow.id == ProjectMemberRow.principal_id)
                    .join(OrgRow, OrgRow.id == GroupRow.org_id)
                    .where(
                        ProjectMemberRow.project_id == project_id, ProjectMemberRow.principal_kind == GROUP_PRINCIPAL
                    )
                )
            ).all()
        people = [
            ProjectAccessRow("user", uid, name, email, role, role is Role.owner)
            for uid, raw, name, email in users
            if (role := _role_or_none(raw)) is not None
        ]
        teams = [
            ProjectAccessRow("group", gid, name, org_name, role, False)
            for gid, raw, name, org_name in groups
            if (role := _role_or_none(raw)) is not None
        ]

        def by_name(row: ProjectAccessRow) -> tuple[str, str]:
            return row.name.casefold(), row.subject_id

        return [
            *head,
            *sorted((p for p in people if p.locked), key=by_name),
            *sorted(teams, key=by_name),
            *sorted((p for p in people if not p.locked), key=by_name),
        ]

    async def candidates(self, project_id: UUID, actor_id: str, query: str, limit: int) -> list[ProjectCandidate]:
        async with self._sessions.use() as session:
            project = (
                await session.execute(
                    select(ProjectRow.owner_user_id, ProjectRow.owner_org_id).where(
                        ProjectRow.id == project_id, ProjectRow.deleted_at.is_(None)
                    )
                )
            ).first()
            if project is None:
                return []
            scope_orgs = _scope_orgs(project.owner_org_id, actor_id)
            needle = query.strip()
            taken = select(ProjectMemberRow.principal_id).where(ProjectMemberRow.project_id == project_id)
            group_filters: list[ColumnElement[bool]] = [
                GroupRow.org_id.in_(scope_orgs),
                GroupRow.id.not_in(taken.where(ProjectMemberRow.principal_kind == GROUP_PRINCIPAL)),
            ]
            if needle:
                group_filters.append(GroupRow.name.ilike(_like(needle), escape="\\"))
            groups = (
                await session.execute(
                    select(GroupRow.id, GroupRow.name, OrgRow.name)
                    .join(OrgRow, OrgRow.id == GroupRow.org_id)
                    .where(*group_filters)
                    .order_by(func.lower(GroupRow.name), GroupRow.id)
                    .limit(limit)
                )
            ).all()
            found: list[ProjectCandidate] = [ProjectCandidate("group", gid, name, org) for gid, name, org in groups]
            room = limit - len(found)
            if room <= 0:
                return found
            visible = _visible_people(project.owner_org_id, actor_id, scope_orgs)
            people_filters: list[ColumnElement[bool]] = [
                visible,
                UserRow.status == UserStatus.active.value,
                UserRow.id != actor_id,
                UserRow.id.not_in(taken.where(ProjectMemberRow.principal_kind == USER_PRINCIPAL)),
            ]
            if project.owner_user_id is not None:
                people_filters.append(UserRow.id != project.owner_user_id)
            if needle:
                like = _like(needle)
                people_filters.append(
                    or_(UserRow.name.ilike(like, escape="\\"), UserRow.email.ilike(like, escape="\\"))
                )
            people = (
                await session.execute(
                    select(UserRow.id, UserRow.name, UserRow.email)
                    .where(*people_filters)
                    .order_by(func.lower(UserRow.name), UserRow.id)
                    .limit(room)
                )
            ).all()
        found.extend(ProjectCandidate("user", uid, name, email) for uid, name, email in people)
        return found

    async def can_share_with(self, project_id: UUID, actor_id: str, user_id: str) -> bool:
        async with self._sessions.use() as session:
            project = (
                await session.execute(
                    select(ProjectRow.owner_org_id).where(ProjectRow.id == project_id, ProjectRow.deleted_at.is_(None))
                )
            ).first()
            if project is None:
                return False
            visible = _visible_people(project.owner_org_id, actor_id, _scope_orgs(project.owner_org_id, actor_id))
            found = await session.execute(select(UserRow.id).where(UserRow.id == user_id, visible))
            return found.first() is not None
