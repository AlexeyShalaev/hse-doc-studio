"""Передачи владения проектом в Postgres."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import aliased

from hse_doc_studio.core.invitations.entities import OwnerKind, ProjectTransfer, TransferStatus, TransferView
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.orm.invitations import ProjectTransferRow
from hse_doc_studio.infra.db.orm.orgs import OrgRow
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.session import SessionProvider

_PENDING = TransferStatus.pending.value
_FromUser = aliased(UserRow)
_FromOrg = aliased(OrgRow)
_ToUser = aliased(UserRow)
_ToOrg = aliased(OrgRow)


def _entity(row: ProjectTransferRow) -> ProjectTransfer:
    return ProjectTransfer(
        id=row.id,
        project_id=row.project_id,
        from_kind=cast(OwnerKind, row.from_kind),
        from_id=row.from_id,
        to_kind=cast(OwnerKind, row.to_kind),
        to_id=row.to_id,
        initiated_by=row.initiated_by,
        message=row.message,
        status=TransferStatus(row.status),
        created_at=row.created_at,
        expires_at=row.expires_at,
        decided_at=row.decided_at,
        decided_by=row.decided_by,
    )


def _view_select() -> Any:
    return (
        select(
            ProjectTransferRow,
            ProjectRow.name.label("project_name"),
            func.coalesce(_FromOrg.name, _FromUser.name, "").label("from_name"),
            func.coalesce(_ToOrg.name, _ToUser.name, "").label("to_name"),
        )
        .join(ProjectRow, ProjectRow.id == ProjectTransferRow.project_id)
        .outerjoin(_FromUser, (ProjectTransferRow.from_kind == "user") & (_FromUser.id == ProjectTransferRow.from_id))
        .outerjoin(_FromOrg, (ProjectTransferRow.from_kind == "org") & (_FromOrg.id == ProjectTransferRow.from_id))
        .outerjoin(_ToUser, (ProjectTransferRow.to_kind == "user") & (_ToUser.id == ProjectTransferRow.to_id))
        .outerjoin(_ToOrg, (ProjectTransferRow.to_kind == "org") & (_ToOrg.id == ProjectTransferRow.to_id))
        .where(ProjectRow.deleted_at.is_(None))
    )


def _view(row: Any) -> TransferView:
    return TransferView(_entity(row[0]), row.project_name, row.from_name, row.to_name)


class PostgresProjectTransferRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def add(self, transfer: ProjectTransfer) -> None:
        async with self._sessions.use() as session:
            session.add(
                ProjectTransferRow(
                    id=transfer.id,
                    project_id=transfer.project_id,
                    from_kind=transfer.from_kind,
                    from_id=transfer.from_id,
                    to_kind=transfer.to_kind,
                    to_id=transfer.to_id,
                    initiated_by=transfer.initiated_by,
                    message=transfer.message,
                    status=transfer.status.value,
                    created_at=transfer.created_at,
                    expires_at=transfer.expires_at,
                    decided_at=transfer.decided_at,
                    decided_by=transfer.decided_by,
                )
            )
            await session.flush()

    async def get(self, transfer_id: str) -> ProjectTransfer | None:
        async with self._sessions.use() as session:
            row = await session.get(ProjectTransferRow, transfer_id)
            return None if row is None else _entity(row)

    async def lock(self, transfer_id: str) -> ProjectTransfer | None:
        stmt = select(ProjectTransferRow).where(ProjectTransferRow.id == transfer_id).with_for_update()
        async with self._sessions.use() as session:
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is not None:
                await session.refresh(row)
            return None if row is None else _entity(row)

    async def update(self, transfer: ProjectTransfer) -> None:
        async with self._sessions.use() as session:
            await session.execute(
                update(ProjectTransferRow)
                .where(ProjectTransferRow.id == transfer.id)
                .values(status=transfer.status.value, decided_at=transfer.decided_at, decided_by=transfer.decided_by)
                .execution_options(synchronize_session=False)
            )

    async def pending_for_project(self, project_id: UUID) -> ProjectTransfer | None:
        stmt = select(ProjectTransferRow).where(
            ProjectTransferRow.project_id == project_id, ProjectTransferRow.status == _PENDING
        )
        async with self._sessions.use() as session:
            row = (await session.execute(stmt)).scalar_one_or_none()
            return None if row is None else _entity(row)

    async def supersede_pending(self, project_id: UUID, now: datetime) -> int:
        stmt = (
            update(ProjectTransferRow)
            .where(ProjectTransferRow.project_id == project_id, ProjectTransferRow.status == _PENDING)
            .values(status=TransferStatus.superseded.value, decided_at=now)
            .returning(ProjectTransferRow.id)
            .execution_options(synchronize_session=False)
        )
        async with self._sessions.use() as session:
            return len((await session.execute(stmt)).all())

    async def view(self, transfer_id: str) -> TransferView | None:
        async with self._sessions.use() as session:
            row = (await session.execute(_view_select().where(ProjectTransferRow.id == transfer_id))).first()
        return None if row is None else _view(row)

    async def list_for_user(self, user_id: str) -> list[TransferView]:
        stmt = (
            _view_select()
            .where(
                ProjectTransferRow.to_kind == "user",
                ProjectTransferRow.to_id == user_id,
                ProjectTransferRow.status == _PENDING,
            )
            .order_by(ProjectTransferRow.created_at.desc(), ProjectTransferRow.id)
            .limit(100)
        )
        async with self._sessions.use() as session:
            return [_view(r) for r in (await session.execute(stmt)).all()]

    async def count_pending_for_user(self, user_id: str, now: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(ProjectTransferRow)
            .where(
                ProjectTransferRow.to_kind == "user",
                ProjectTransferRow.to_id == user_id,
                ProjectTransferRow.status == _PENDING,
                ProjectTransferRow.expires_at > now,
            )
        )
        async with self._sessions.use() as session:
            return int((await session.execute(stmt)).scalar_one())
