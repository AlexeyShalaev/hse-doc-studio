"""Членство проекта в Postgres: владелец, организация, прямые участники и группы."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from hse_doc_studio.core.access.entities import Actor, ActorKind, Grant, ProjectAcl, Role
from hse_doc_studio.core.access.repositories import (
    IProjectAclRepository,
    ProjectMemberGrant,
    ProjectMembership,
    ProjectOwnerView,
)
from hse_doc_studio.core.access.resolution import OrgStanding, resolve_grant
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.orm.orgs import GroupMemberRow, OrgMemberRow, OrgRow
from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow, ProjectRow
from hse_doc_studio.infra.db.repositories.projects import GROUP_PRINCIPAL, USER_PRINCIPAL
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.projects.acl_flags import AclFlags, AclFlagsCache

logger = structlog.get_logger()

_ORG_ADMIN_ROLES = frozenset({"owner", "admin"})


class PostgresProjectAclRepository:
    """Права берутся из Postgres на каждый вызов: владение, роль организации, прямая запись, группы.
    Между запросами ничего не кэшируется, поэтому вышедший из группы теряет доступ сразу."""

    def __init__(self, sessions: SessionProvider, flags: AclFlagsCache) -> None:
        self._sessions = sessions
        self._flags = flags

    async def load_for(self, actor: Actor, project_id: UUID, *, include_links: bool = True) -> ProjectAcl | None:  # noqa: ARG002
        if actor.kind is not ActorKind.user or actor.id is None:
            return None
        async with self._sessions.use() as session:
            project = (
                await session.execute(
                    select(
                        ProjectRow.id,
                        ProjectRow.owner_user_id,
                        ProjectRow.owner_org_id,
                        ProjectRow.org_visible,
                        ProjectRow.team,
                        ProjectRow.shared_enabled,
                    ).where(ProjectRow.id == project_id, ProjectRow.deleted_at.is_(None))
                )
            ).first()
            if project is None:
                return None
            self._flags.put(project_id, AclFlags(team=project.team, shared_enabled=project.shared_enabled))
            grants = await _grants(session, actor.id, [project])
        grant = grants.get(project_id)
        if grant is None:
            return None
        return ProjectAcl(
            project_id=str(project_id),
            owner_id=project.owner_user_id,
            team=project.team,
            shared_enabled=project.shared_enabled,
            grants={actor.id: grant},
        )

    async def memberships_for(self, actor: Actor, project_ids: Sequence[UUID]) -> dict[UUID, ProjectMembership]:
        if actor.kind is not ActorKind.user or actor.id is None or not project_ids:
            return {}
        stmt = (
            select(
                ProjectRow.id,
                ProjectRow.owner_user_id,
                ProjectRow.owner_org_id,
                ProjectRow.org_visible,
                UserRow.name.label("owner_name"),
                OrgRow.name.label("org_name"),
                OrgRow.slug.label("org_slug"),
            )
            .select_from(ProjectRow)
            .outerjoin(UserRow, UserRow.id == ProjectRow.owner_user_id)
            .outerjoin(OrgRow, OrgRow.id == ProjectRow.owner_org_id)
            .where(ProjectRow.id.in_(list(project_ids)), ProjectRow.deleted_at.is_(None))
        )
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).all()
            grants = await _grants(session, actor.id, rows)
        result: dict[UUID, ProjectMembership] = {}
        for row in rows:
            grant = grants.get(row.id)
            if grant is None:
                continue
            result[row.id] = ProjectMembership(project_id=row.id, owner=_owner_view(row), my_role=grant.role)
        return result

    async def set_shared_enabled(self, project_id: UUID, enabled: bool) -> None:
        stmt = update(ProjectRow).where(ProjectRow.id == project_id).values(shared_enabled=enabled)
        async with self._sessions.use() as session:
            await session.execute(stmt)
        current = self._flags.get(project_id)
        if current is not None:
            self._flags.put(project_id, AclFlags(team=current.team, shared_enabled=enabled))


async def _grants(session: AsyncSession, user_id: str, projects: Sequence[Any]) -> dict[UUID, Grant]:
    """Право человека на каждый из проектов; строки проектов несут id, владельцев и org_visible."""
    ids = [p.id for p in projects]
    direct = await _direct_grants(session, user_id, ids)
    via_groups = await _group_grants(session, user_id, ids)
    org_roles = await _org_roles(session, user_id, {p.owner_org_id for p in projects if p.owner_org_id is not None})
    grants: dict[UUID, Grant] = {}
    for project in projects:
        org_role = org_roles.get(project.owner_org_id) if project.owner_org_id is not None else None
        standing = (
            None
            if org_role is None
            else OrgStanding(is_admin=org_role in _ORG_ADMIN_ROLES, org_visible=bool(project.org_visible))
        )
        grant = resolve_grant(
            is_owner=project.owner_user_id == user_id,
            direct=direct.get(project.id),
            groups=via_groups.get(project.id, ()),
            org=standing,
        )
        if grant is not None:
            grants[project.id] = grant
    return grants


async def _direct_grants(session: AsyncSession, user_id: str, ids: list[UUID]) -> dict[UUID, ProjectMemberGrant]:
    stmt = select(ProjectMemberRow).where(
        ProjectMemberRow.project_id.in_(ids),
        ProjectMemberRow.principal_kind == USER_PRINCIPAL,
        ProjectMemberRow.principal_id == user_id,
    )
    found = ((row.project_id, member_grant_of(row)) for row in (await session.execute(stmt)).scalars())
    return {pid: grant for pid, grant in found if grant is not None}


async def _group_grants(session: AsyncSession, user_id: str, ids: list[UUID]) -> dict[UUID, list[ProjectMemberGrant]]:
    stmt = (
        select(ProjectMemberRow)
        .join(
            GroupMemberRow,
            and_(GroupMemberRow.group_id == ProjectMemberRow.principal_id, GroupMemberRow.user_id == user_id),
        )
        .where(ProjectMemberRow.project_id.in_(ids), ProjectMemberRow.principal_kind == GROUP_PRINCIPAL)
    )
    result: dict[UUID, list[ProjectMemberGrant]] = {}
    for row in (await session.execute(stmt)).scalars():
        if (grant := member_grant_of(row)) is not None:
            result.setdefault(row.project_id, []).append(grant)
    return result


async def _org_roles(session: AsyncSession, user_id: str, org_ids: set[str]) -> dict[str, str]:
    if not org_ids:
        return {}
    stmt = select(OrgMemberRow.org_id, OrgMemberRow.role).where(
        OrgMemberRow.user_id == user_id, OrgMemberRow.org_id.in_(org_ids)
    )
    return {row.org_id: row.role for row in await session.execute(stmt)}


def member_grant_of(row: ProjectMemberRow) -> ProjectMemberGrant | None:
    """Непонятная роль в БД не открывает ничего."""
    try:
        role = Role(row.role)
    except ValueError:
        logger.warning("project acl: unknown role in project_members", role=row.role)
        return None
    return ProjectMemberGrant(
        principal_kind="group" if row.principal_kind == GROUP_PRINCIPAL else "user",
        principal_id=row.principal_id,
        role=role,
        persona=row.persona,
        can_share=row.can_share,
        show_sources=row.show_sources,
        can_edit_all=row.can_edit_all,
    )


def _owner_view(row: Any) -> ProjectOwnerView:
    if row.owner_user_id is not None:
        return ProjectOwnerView(kind="user", id=row.owner_user_id, name=row.owner_name or "", slug=None)
    return ProjectOwnerView(
        kind="org", id=row.owner_org_id or "", name=row.org_name or row.owner_org_id or "", slug=row.org_slug
    )


class RequestAclCache:
    """Кэш одного запроса: гард и сценарии спрашивают права одного проекта несколько раз."""

    def __init__(self, inner: IProjectAclRepository) -> None:
        self._inner = inner
        self._loaded: dict[tuple[str | None, UUID, bool], ProjectAcl | None] = {}

    async def load_for(self, actor: Actor, project_id: UUID, *, include_links: bool = True) -> ProjectAcl | None:
        key = (actor.key, project_id, include_links)
        if key not in self._loaded:
            self._loaded[key] = await self._inner.load_for(actor, project_id, include_links=include_links)
        return self._loaded[key]

    async def set_shared_enabled(self, project_id: UUID, enabled: bool) -> None:
        await self._inner.set_shared_enabled(project_id, enabled)
        self._loaded = {k: v for k, v in self._loaded.items() if k[1] != project_id}
