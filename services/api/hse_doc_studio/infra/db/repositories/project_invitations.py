"""Приглашения в проект в Postgres: запись, поиск ожидающих, списки для проекта и для адресата."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import aliased

from hse_doc_studio.core.access.entities import Role
from hse_doc_studio.core.invitations.entities import (
    InvitationStatus,
    InvitationView,
    MemberTerms,
    MyInvitationView,
    ProjectInvitation,
)
from hse_doc_studio.core.listing import Found, Window
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.orm.invitations import ProjectInvitationRow
from hse_doc_studio.infra.db.orm.orgs import OrgRow
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.session import SessionProvider

_PENDING = InvitationStatus.pending.value


def to_entity(row: ProjectInvitationRow) -> ProjectInvitation:
    return ProjectInvitation(
        id=row.id,
        project_id=row.project_id,
        invitee_user_id=row.invitee_user_id,
        invitee_email=row.invitee_email,
        terms=MemberTerms(
            role=Role(row.role),
            persona=row.persona,
            can_share=row.can_share,
            show_sources=row.show_sources,
            can_edit_all=row.can_edit_all,
        ),
        message=row.message,
        token_hash=row.token_hash,
        invited_by=row.invited_by,
        created_at=row.created_at,
        expires_at=row.expires_at,
        status=InvitationStatus(row.status),
        last_sent_at=row.last_sent_at,
        sent_count=row.sent_count,
        decided_at=row.decided_at,
        registration_invite_id=row.registration_invite_id,
    )


def _values(inv: ProjectInvitation) -> dict[str, Any]:
    return {
        "project_id": inv.project_id,
        "invitee_user_id": inv.invitee_user_id,
        "invitee_email": inv.invitee_email,
        "role": inv.terms.role.value,
        "persona": inv.terms.persona,
        "can_share": inv.terms.can_share,
        "show_sources": inv.terms.show_sources,
        "can_edit_all": inv.terms.can_edit_all,
        "message": inv.message,
        "token_hash": inv.token_hash,
        "invited_by": inv.invited_by,
        "created_at": inv.created_at,
        "expires_at": inv.expires_at,
        "status": inv.status.value,
        "decided_at": inv.decided_at,
        "sent_count": inv.sent_count,
        "last_sent_at": inv.last_sent_at,
        "registration_invite_id": inv.registration_invite_id,
    }


_Invitee = aliased(UserRow)
_Inviter = aliased(UserRow)
_Owner = aliased(UserRow)


def _my_select() -> Any:
    return (
        select(
            ProjectInvitationRow,
            ProjectRow.name.label("project_name"),
            func.coalesce(OrgRow.name, _Owner.name, "").label("owner_name"),
            _Inviter.name.label("inviter_name"),
        )
        .join(ProjectRow, ProjectRow.id == ProjectInvitationRow.project_id)
        .outerjoin(_Owner, _Owner.id == ProjectRow.owner_user_id)
        .outerjoin(OrgRow, OrgRow.id == ProjectRow.owner_org_id)
        .outerjoin(_Inviter, _Inviter.id == ProjectInvitationRow.invited_by)
        .where(ProjectRow.deleted_at.is_(None))
    )


def _my_view(row: Any) -> MyInvitationView:
    return MyInvitationView(
        invitation=to_entity(row[0]),
        project_name=row.project_name,
        owner_name=row.owner_name,
        inviter_name=row.inviter_name,
    )


class PostgresProjectInvitationRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def add(self, invitation: ProjectInvitation) -> None:
        async with self._sessions.use() as session:
            session.add(ProjectInvitationRow(id=invitation.id, **_values(invitation)))
            await session.flush()

    async def get(self, invitation_id: str) -> ProjectInvitation | None:
        async with self._sessions.use() as session:
            row = await session.get(ProjectInvitationRow, invitation_id)
            return None if row is None else to_entity(row)

    async def get_by_token_hash(self, token_hash: str) -> ProjectInvitation | None:
        stmt = select(ProjectInvitationRow).where(ProjectInvitationRow.token_hash == token_hash)
        async with self._sessions.use() as session:
            row = (await session.execute(stmt)).scalar_one_or_none()
            return None if row is None else to_entity(row)

    async def lock(self, invitation_id: str) -> ProjectInvitation | None:
        stmt = select(ProjectInvitationRow).where(ProjectInvitationRow.id == invitation_id).with_for_update()
        async with self._sessions.use() as session:
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is not None:
                await session.refresh(row)
            return None if row is None else to_entity(row)

    async def update(self, invitation: ProjectInvitation) -> None:
        async with self._sessions.use() as session:
            await session.execute(
                update(ProjectInvitationRow)
                .where(ProjectInvitationRow.id == invitation.id)
                .values(**_values(invitation))
                .execution_options(synchronize_session=False)
            )

    async def pending_for_user(self, project_id: UUID, user_id: str) -> ProjectInvitation | None:
        return await self._one_pending(ProjectInvitationRow.invitee_user_id == user_id, project_id)

    async def pending_for_email(self, project_id: UUID, email: str) -> ProjectInvitation | None:
        return await self._one_pending(ProjectInvitationRow.invitee_email == email, project_id)

    async def _one_pending(self, condition: Any, project_id: UUID) -> ProjectInvitation | None:
        stmt = select(ProjectInvitationRow).where(
            ProjectInvitationRow.project_id == project_id, ProjectInvitationRow.status == _PENDING, condition
        )
        async with self._sessions.use() as session:
            row = (await session.execute(stmt.limit(1))).scalar_one_or_none()
            return None if row is None else to_entity(row)

    async def count_pending(self, project_id: UUID, now: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(ProjectInvitationRow)
            .where(
                ProjectInvitationRow.project_id == project_id,
                ProjectInvitationRow.status == _PENDING,
                ProjectInvitationRow.expires_at > now,
            )
        )
        async with self._sessions.use() as session:
            return int((await session.execute(stmt)).scalar_one())

    async def page_for_project(self, project_id: UUID, *, pending_only: bool, window: Window) -> Found[InvitationView]:
        where = [ProjectInvitationRow.project_id == project_id]
        if pending_only:
            where.append(ProjectInvitationRow.status == _PENDING)
        stmt = (
            select(ProjectInvitationRow, _Invitee.name.label("invitee_name"), _Inviter.name.label("inviter_name"))
            .outerjoin(_Invitee, _Invitee.id == ProjectInvitationRow.invitee_user_id)
            .outerjoin(_Inviter, _Inviter.id == ProjectInvitationRow.invited_by)
            .where(*where)
            .order_by(ProjectInvitationRow.created_at.desc(), ProjectInvitationRow.id)
        )
        async with self._sessions.use() as session:
            total = (
                await session.execute(select(func.count()).select_from(ProjectInvitationRow).where(*where))
            ).scalar_one()
            rows = (await session.execute(stmt.limit(window.limit).offset(window.offset))).all()
        return Found(
            [InvitationView(to_entity(r[0]), r.invitee_name, r.inviter_name) for r in rows],
            int(total),
        )

    async def list_for_user(self, user_id: str) -> list[MyInvitationView]:
        stmt = (
            _my_select()
            .where(ProjectInvitationRow.invitee_user_id == user_id, ProjectInvitationRow.status == _PENDING)
            .order_by(ProjectInvitationRow.created_at.desc(), ProjectInvitationRow.id)
            .limit(200)
        )
        async with self._sessions.use() as session:
            return [_my_view(r) for r in (await session.execute(stmt)).all()]

    async def my_view(self, invitation_id: str) -> MyInvitationView | None:
        async with self._sessions.use() as session:
            row = (await session.execute(_my_select().where(ProjectInvitationRow.id == invitation_id))).first()
        return None if row is None else _my_view(row)

    async def attach_email(self, email: str, user_id: str) -> list[ProjectInvitation]:
        # Если человеку в том же проекте уже ждёт приглашение по id, почтовое остаётся непривязанным:
        # двух ожидающих одному человеку в проекте не бывает (уникальный индекс).
        other = aliased(ProjectInvitationRow)
        already = (
            select(other.id)
            .where(
                other.project_id == ProjectInvitationRow.project_id,
                other.invitee_user_id == user_id,
                other.status == _PENDING,
            )
            .exists()
        )
        stmt = (
            update(ProjectInvitationRow)
            .where(
                ProjectInvitationRow.invitee_email == email,
                ProjectInvitationRow.invitee_user_id.is_(None),
                ProjectInvitationRow.status == _PENDING,
                ~already,
            )
            .values(invitee_user_id=user_id)
            .returning(ProjectInvitationRow)
            .execution_options(synchronize_session=False)
        )
        async with self._sessions.use() as session:
            return [to_entity(r) for r in (await session.execute(stmt)).scalars().all()]

    async def count_pending_for_user(self, user_id: str, now: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(ProjectInvitationRow)
            .join(ProjectRow, ProjectRow.id == ProjectInvitationRow.project_id)
            .where(
                ProjectInvitationRow.invitee_user_id == user_id,
                ProjectInvitationRow.status == _PENDING,
                ProjectInvitationRow.expires_at > now,
                ProjectRow.deleted_at.is_(None),
            )
        )
        async with self._sessions.use() as session:
            return int((await session.execute(stmt)).scalar_one())
