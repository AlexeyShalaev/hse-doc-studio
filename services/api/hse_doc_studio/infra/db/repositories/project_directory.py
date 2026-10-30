"""Панель «Доступ» проекта: кто имеет доступ и кого можно добавить. Чужих людей по всей установке не перебрать."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    CompoundSelect,
    Select,
    case,
    false,
    func,
    literal,
    null,
    or_,
    select,
    true,
    union_all,
)

from hse_doc_studio.core.access.entities import Role
from hse_doc_studio.core.access.repositories import (
    ACCESS_ROLE_ORDER,
    AccessQuery,
    ProjectAccessRow,
    ProjectCandidate,
    TransferCandidate,
)
from hse_doc_studio.core.identity.entities import UserStatus
from hse_doc_studio.core.listing import Found, Picked
from hse_doc_studio.core.orgs.entities import OrgRole
from hse_doc_studio.infra.db.listing import Expr, contains, contains_lower, fetch_page, ordering
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


_ORG_MANAGERS = (OrgRole.owner.value, OrgRole.admin.value)


def _role_rank(role: Expr) -> ColumnElement[int]:
    return case({r.value: i for i, r in enumerate(ACCESS_ROLE_ORDER)}, value=role, else_=len(ACCESS_ROLE_ORDER))


def _transfer_orgs(actor_id: str, owner_org_id: str | None, needle: str) -> Select[str, str]:
    """Организации, где смотрящий владелец или админ; нынешняя организация-владелец не предлагается."""
    managed = select(OrgMemberRow.org_id).where(OrgMemberRow.user_id == actor_id, OrgMemberRow.role.in_(_ORG_MANAGERS))
    stmt = select(OrgRow.slug, OrgRow.name).where(OrgRow.id.in_(managed))
    if owner_org_id is not None:
        stmt = stmt.where(OrgRow.id != owner_org_id)
    if needle:
        stmt = stmt.where(contains(needle, OrgRow.name, OrgRow.slug))
    return stmt.order_by(func.lower(OrgRow.name), OrgRow.id)


def _transfer_people(actor_id: str, owner_user_id: str | None, needle: str) -> Select[str, str, str]:
    """Активные люди общих со смотрящим организаций, кроме него самого и нынешнего владельца."""
    mine = select(OrgMemberRow.org_id).where(OrgMemberRow.user_id == actor_id)
    shared = select(OrgMemberRow.user_id).where(OrgMemberRow.org_id.in_(mine))
    stmt = select(UserRow.id, UserRow.name, UserRow.email).where(
        UserRow.id.in_(shared), UserRow.status == UserStatus.active.value, UserRow.id != actor_id
    )
    if owner_user_id is not None:
        stmt = stmt.where(UserRow.id != owner_user_id)
    if needle:
        stmt = stmt.where(contains_lower(needle, func.lower(UserRow.name), UserRow.email_normalized))
    return stmt.order_by(func.lower(UserRow.name), UserRow.id)


def _access_rows(project_id: UUID, owner_user_id: str | None) -> CompoundSelect[Any]:
    """Все строки «Доступа» одним запросом: владелец (pin 0), организация-владелец (1), владельцы-участники (2)
    и остальные люди и группы (3). Закреплённые нельзя менять в панели (`locked`)."""
    owner = (
        select(
            literal("user").label("kind"),
            UserRow.id.label("id"),
            UserRow.name.label("name"),
            UserRow.email.label("detail"),
            literal(Role.owner.value).label("role"),
            true().label("locked"),
            literal(0).label("pin"),
        )
        .join(ProjectRow, ProjectRow.owner_user_id == UserRow.id)
        .where(ProjectRow.id == project_id)
    )
    org = (
        select(
            literal("org"),
            OrgRow.id,
            OrgRow.name,
            null(),
            literal(Role.reader.value),
            true(),
            literal(1),
        )
        .join(ProjectRow, ProjectRow.owner_org_id == OrgRow.id)
        .where(ProjectRow.id == project_id)
    )
    is_owner = ProjectMemberRow.role == Role.owner.value
    people = (
        select(
            literal("user"),
            ProjectMemberRow.principal_id,
            UserRow.name,
            UserRow.email,
            ProjectMemberRow.role,
            is_owner,
            case((is_owner, literal(2)), else_=literal(3)),
        )
        .join(UserRow, UserRow.id == ProjectMemberRow.principal_id)
        .where(
            ProjectMemberRow.project_id == project_id,
            ProjectMemberRow.principal_kind == USER_PRINCIPAL,
            ProjectMemberRow.principal_id != (owner_user_id or ""),
        )
    )
    groups = (
        select(
            literal("group"),
            ProjectMemberRow.principal_id,
            GroupRow.name,
            OrgRow.name,
            ProjectMemberRow.role,
            false(),
            literal(3),
        )
        .join(GroupRow, GroupRow.id == ProjectMemberRow.principal_id)
        .join(OrgRow, OrgRow.id == GroupRow.org_id)
        .where(ProjectMemberRow.project_id == project_id, ProjectMemberRow.principal_kind == GROUP_PRINCIPAL)
    )
    return union_all(owner, org, people, groups)


class PostgresProjectAccessDirectory:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def page_access(self, project_id: UUID, query: AccessQuery) -> Found[ProjectAccessRow] | None:
        async with self._sessions.use() as session:
            project = (
                await session.execute(
                    select(ProjectRow.owner_user_id, ProjectRow.owner_org_id).where(
                        ProjectRow.id == project_id, ProjectRow.deleted_at.is_(None)
                    )
                )
            ).first()
            if project is None:
                return None
            rows = _access_rows(project_id, project.owner_user_id).subquery("access")
            stmt = select(rows).where(rows.c.role.in_([r.value for r in Role]))
            if query.q:
                stmt = stmt.where(contains(query.q, rows.c.name, rows.c.detail))
            if query.kinds:
                stmt = stmt.where(rows.c.kind.in_(query.kinds))
            if query.roles:
                stmt = stmt.where(rows.c.role.in_([r.value for r in query.roles]))
            sort = {"name": func.lower(rows.c.name), "role": _role_rank(rows.c.role)}
            # Закреплённые строки всегда первыми, поэтому они всегда на первой странице.
            stmt = stmt.order_by(rows.c.pin, *ordering(query.sort, sort, rows.c.kind, rows.c.id))
            found, total = await fetch_page(session, stmt, query.window)
        return Found([ProjectAccessRow(r.kind, r.id, r.name, r.detail, Role(r.role), r.locked) for r in found], total)

    async def candidates(
        self,
        project_id: UUID,
        actor_id: str,
        query: str,
        limit: int,
        kind: Literal["user", "group"] | None = None,
    ) -> Picked[ProjectCandidate]:
        # Читаем на одну строку больше `limit`: лишняя говорит, что стоит уточнить поиск.
        wanted = limit + 1
        async with self._sessions.use() as session:
            project = (
                await session.execute(
                    select(ProjectRow.owner_user_id, ProjectRow.owner_org_id).where(
                        ProjectRow.id == project_id, ProjectRow.deleted_at.is_(None)
                    )
                )
            ).first()
            if project is None:
                return Picked([], has_more=False)
            scope_orgs = _scope_orgs(project.owner_org_id, actor_id)
            needle = query.strip()
            taken = select(ProjectMemberRow.principal_id).where(ProjectMemberRow.project_id == project_id)
            found: list[ProjectCandidate] = []
            if kind != "user":
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
                        .limit(wanted)
                    )
                ).all()
                found += [ProjectCandidate("group", gid, name, org) for gid, name, org in groups]
            room = wanted - len(found)
            if kind != "group" and room > 0:
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
                found += [ProjectCandidate("user", uid, name, email) for uid, name, email in people]
        return Picked.of(found, limit)

    async def transfer_candidates(
        self, project_id: UUID, actor_id: str, query: str, limit: int, kind: Literal["user", "org"] | None = None
    ) -> Picked[TransferCandidate]:
        wanted = limit + 1
        needle = query.strip()
        async with self._sessions.use() as session:
            project = (
                await session.execute(
                    select(ProjectRow.owner_user_id, ProjectRow.owner_org_id).where(
                        ProjectRow.id == project_id, ProjectRow.deleted_at.is_(None)
                    )
                )
            ).first()
            if project is None:
                return Picked([], has_more=False)
            found: list[TransferCandidate] = []
            if kind != "user":
                orgs = await session.execute(_transfer_orgs(actor_id, project.owner_org_id, needle).limit(wanted))
                found += [TransferCandidate("org", slug, name, slug) for slug, name in orgs.all()]
            room = wanted - len(found)
            if kind != "org" and room > 0:
                people = await session.execute(_transfer_people(actor_id, project.owner_user_id, needle).limit(room))
                found += [TransferCandidate("user", uid, name, email) for uid, name, email in people.all()]
        return Picked.of(found, limit)

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
