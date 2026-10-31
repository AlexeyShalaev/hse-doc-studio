"""Запросы доступа к проекту в Postgres."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import aliased

from hse_doc_studio.core.access.entities import Role
from hse_doc_studio.core.invitations.entities import (
    AccessRequest,
    AccessRequestStatus,
    AccessRequestView,
    MyAccessRequestView,
)
from hse_doc_studio.core.listing import Found, Window
from hse_doc_studio.core.orgs.entities import OrgRole
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.orm.invitations import AccessRequestRow
from hse_doc_studio.infra.db.orm.orgs import OrgMemberRow
from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow, ProjectRow
from hse_doc_studio.infra.db.session import SessionProvider

_PENDING = AccessRequestStatus.pending.value
_Requester = aliased(UserRow)
_Decider = aliased(UserRow)


def _entity(row: AccessRequestRow) -> AccessRequest:
    return AccessRequest(
        id=row.id,
        project_id=row.project_id,
        user_id=row.user_id,
        message=row.message,
        status=AccessRequestStatus(row.status),
        created_at=row.created_at,
        decided_at=row.decided_at,
        decided_by=row.decided_by,
        granted_role=Role(row.granted_role) if row.granted_role else None,
    )


def _view_select() -> Any:
    return (
        select(
            AccessRequestRow,
            _Requester.name.label("name"),
            _Requester.email.label("email"),
            _Decider.name.label("decider_name"),
        )
        .join(_Requester, _Requester.id == AccessRequestRow.user_id)
        .outerjoin(_Decider, _Decider.id == AccessRequestRow.decided_by)
    )


def _view(row: Any) -> AccessRequestView:
    return AccessRequestView(_entity(row[0]), row.name, row.email, row.decider_name)


class PostgresAccessRequestRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def add(self, request: AccessRequest) -> None:
        async with self._sessions.use() as session:
            session.add(
                AccessRequestRow(
                    id=request.id,
                    project_id=request.project_id,
                    user_id=request.user_id,
                    message=request.message,
                    status=request.status.value,
                    created_at=request.created_at,
                )
            )
            await session.flush()

    async def get(self, request_id: str) -> AccessRequest | None:
        async with self._sessions.use() as session:
            row = await session.get(AccessRequestRow, request_id)
            return None if row is None else _entity(row)

    async def lock(self, request_id: str) -> AccessRequest | None:
        stmt = select(AccessRequestRow).where(AccessRequestRow.id == request_id).with_for_update()
        async with self._sessions.use() as session:
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is not None:
                await session.refresh(row)
            return None if row is None else _entity(row)

    async def update(self, request: AccessRequest) -> None:
        async with self._sessions.use() as session:
            await session.execute(
                update(AccessRequestRow)
                .where(AccessRequestRow.id == request.id)
                .values(
                    status=request.status.value,
                    decided_at=request.decided_at,
                    decided_by=request.decided_by,
                    granted_role=request.granted_role.value if request.granted_role else None,
                )
                .execution_options(synchronize_session=False)
            )

    async def pending_for(self, project_id: UUID, user_id: str) -> AccessRequest | None:
        stmt = select(AccessRequestRow).where(
            AccessRequestRow.project_id == project_id,
            AccessRequestRow.user_id == user_id,
            AccessRequestRow.status == _PENDING,
        )
        async with self._sessions.use() as session:
            row = (await session.execute(stmt)).scalar_one_or_none()
            return None if row is None else _entity(row)

    async def last_denied_at(self, project_id: UUID, user_id: str) -> datetime | None:
        stmt = select(func.max(AccessRequestRow.decided_at)).where(
            AccessRequestRow.project_id == project_id,
            AccessRequestRow.user_id == user_id,
            AccessRequestRow.status == AccessRequestStatus.denied.value,
        )
        async with self._sessions.use() as session:
            return (await session.execute(stmt)).scalar_one_or_none()

    async def page_for_project(
        self, project_id: UUID, *, pending_only: bool, window: Window
    ) -> Found[AccessRequestView]:
        where = [AccessRequestRow.project_id == project_id]
        if pending_only:
            where.append(AccessRequestRow.status == _PENDING)
        async with self._sessions.use() as session:
            total = (
                await session.execute(select(func.count()).select_from(AccessRequestRow).where(*where))
            ).scalar_one()
            rows = (
                await session.execute(
                    _view_select()
                    .where(*where)
                    .order_by(AccessRequestRow.created_at.desc(), AccessRequestRow.id)
                    .limit(window.limit)
                    .offset(window.offset)
                )
            ).all()
        return Found([_view(r) for r in rows], int(total))

    async def view(self, request_id: str) -> AccessRequestView | None:
        async with self._sessions.use() as session:
            row = (await session.execute(_view_select().where(AccessRequestRow.id == request_id))).first()
        return None if row is None else _view(row)

    async def list_for_user(self, user_id: str) -> list[MyAccessRequestView]:
        stmt = (
            select(AccessRequestRow, ProjectRow.name)
            .join(ProjectRow, ProjectRow.id == AccessRequestRow.project_id)
            .where(AccessRequestRow.user_id == user_id, ProjectRow.deleted_at.is_(None))
            .order_by(AccessRequestRow.created_at.desc(), AccessRequestRow.id)
            .limit(100)
        )
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).all()
        return [
            MyAccessRequestView(_entity(row), name if row.status == AccessRequestStatus.approved.value else None)
            for row, name in rows
        ]

    async def count_pending_managed(self, user_id: str) -> int:
        managed_orgs = select(OrgMemberRow.org_id).where(
            OrgMemberRow.user_id == user_id, OrgMemberRow.role.in_((OrgRole.owner.value, OrgRole.admin.value))
        )
        sharing = select(ProjectMemberRow.project_id).where(
            ProjectMemberRow.principal_kind == "user",
            ProjectMemberRow.principal_id == user_id,
            ProjectMemberRow.role == Role.editor.value,
            ProjectMemberRow.can_share.is_(True),
        )
        stmt = (
            select(func.count())
            .select_from(AccessRequestRow)
            .join(ProjectRow, ProjectRow.id == AccessRequestRow.project_id)
            .where(
                AccessRequestRow.status == _PENDING,
                ProjectRow.deleted_at.is_(None),
                or_(
                    ProjectRow.owner_user_id == user_id,
                    ProjectRow.owner_org_id.in_(managed_orgs),
                    ProjectRow.id.in_(sharing),
                ),
            )
        )
        async with self._sessions.use() as session:
            return int((await session.execute(stmt)).scalar_one())
