"""Люди проекта для маршрута подписания (docs/design/signing-route.md, 6.5): персоны, приглашения, имена.

Персоны участников берутся из их права на проект (`IProjectAclRepository`), как у подписи слота: так владелец
solo-проекта остаётся автором, а ушедший из проекта человек персон не имеет.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.invitations.entities import mask_email
from hse_doc_studio.core.signatures.plan import AUTHOR_PERSONA
from hse_doc_studio.core.signing_route.ports import RouteCandidate, RouteInvitee
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.orm.invitations import ProjectInvitationRow
from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow, ProjectRow
from hse_doc_studio.infra.db.session import SessionProvider

_ACTIVE = "active"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


class PostgresRoutePeople:
    def __init__(
        self, sessions: SessionProvider, acl: IProjectAclRepository, clock: Callable[[], datetime] = _utc_now
    ) -> None:
        self._sessions = sessions
        self._acl = acl
        self._clock = clock

    async def candidates(self, project_id: UUID) -> list[RouteCandidate]:
        owner_stmt = (
            select(ProjectRow.owner_user_id, ProjectRow.team, UserRow.name, UserRow.status)
            .outerjoin(UserRow, UserRow.id == ProjectRow.owner_user_id)
            .where(ProjectRow.id == project_id, ProjectRow.deleted_at.is_(None))
        )
        members_stmt = (
            select(ProjectMemberRow.principal_id, ProjectMemberRow.persona, UserRow.name)
            .join(UserRow, UserRow.id == ProjectMemberRow.principal_id)
            .where(
                ProjectMemberRow.project_id == project_id,
                ProjectMemberRow.principal_kind == "user",
                ProjectMemberRow.persona.is_not(None),
                UserRow.status == _ACTIVE,
            )
            .order_by(ProjectMemberRow.created_at, ProjectMemberRow.principal_id)
        )
        async with self._sessions.use() as session:
            owner = (await session.execute(owner_stmt)).first()
            members = (await session.execute(members_stmt)).all()
        if owner is None:
            return []
        found: list[RouteCandidate] = []
        if owner.owner_user_id and not owner.team and owner.status == _ACTIVE:
            owner_id = _uuid(owner.owner_user_id)
            if owner_id is not None:
                found.append(RouteCandidate(owner_id, owner.name or "", AUTHOR_PERSONA))
        for principal_id, persona, name in members:
            user_id = _uuid(principal_id)
            if user_id is not None and persona and RouteCandidate(user_id, name, persona) not in found:
                found.append(RouteCandidate(user_id, name, persona))
        return found

    async def invitees(self, project_id: UUID) -> list[RouteInvitee]:
        stmt = (
            select(
                ProjectInvitationRow.id, ProjectInvitationRow.persona, ProjectInvitationRow.invitee_email, UserRow.name
            )
            .outerjoin(UserRow, UserRow.id == ProjectInvitationRow.invitee_user_id)
            .where(
                ProjectInvitationRow.project_id == project_id,
                ProjectInvitationRow.status == "pending",
                ProjectInvitationRow.expires_at > self._clock(),
                ProjectInvitationRow.persona.is_not(None),
            )
            .order_by(ProjectInvitationRow.created_at.desc(), ProjectInvitationRow.id)
        )
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).all()
        return [RouteInvitee(row.id, row.persona, row.name or mask_email(row.invitee_email)) for row in rows]

    async def personas(self, project_id: UUID, user_ids: Collection[UUID]) -> dict[UUID, frozenset[str]]:
        result: dict[UUID, frozenset[str]] = {}
        for user_id in dict.fromkeys(user_ids):
            actor = Actor.user(user_id.hex)
            acl = await self._acl.load_for(actor, project_id, include_links=False)
            grant = acl.grant_for(actor) if acl is not None else None
            if acl is None or grant is None:
                result[user_id] = frozenset()
                continue
            personas = {grant.persona_slug} if grant.persona_slug else set()
            if grant.role is Role.owner and not acl.team:
                personas.add(AUTHOR_PERSONA)
            result[user_id] = frozenset(personas)
        return result

    async def names(self, user_ids: Collection[UUID]) -> dict[UUID, str]:
        ids = {user_id.hex: user_id for user_id in user_ids}
        if not ids:
            return {}
        async with self._sessions.use() as session:
            rows = (await session.execute(select(UserRow.id, UserRow.name).where(UserRow.id.in_(list(ids))))).all()
        return {ids[row.id]: row.name for row in rows if row.id in ids}
