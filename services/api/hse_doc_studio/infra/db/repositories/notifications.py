"""Уведомления «Входящих» в Postgres: дозапись с ключом повтора, страницы, отметка прочитанного, уборка."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.invitations.entities import Notification, NotificationKind, NotificationPayload
from hse_doc_studio.core.listing import Found, Window
from hse_doc_studio.infra.db.orm.invitations import NotificationRow
from hse_doc_studio.infra.db.session import SessionProvider

_PAYLOAD_FIELDS = tuple(NotificationPayload.__dataclass_fields__)


def _payload(raw: Any) -> NotificationPayload:
    data = raw if isinstance(raw, dict) else {}
    return NotificationPayload(**{k: (str(data[k]) if data.get(k) is not None else None) for k in _PAYLOAD_FIELDS})


def _to_entity(row: NotificationRow) -> Notification:
    return Notification(
        id=row.id,
        user_id=row.user_id,
        kind=NotificationKind(row.kind),
        payload=_payload(row.payload),
        created_at=row.created_at,
        read_at=row.read_at,
    )


class PostgresNotificationRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def add(
        self,
        user_id: str,
        kind: NotificationKind,
        payload: NotificationPayload,
        *,
        dedupe_key: str | None = None,
        now: datetime | None = None,
    ) -> None:
        moment = now or datetime.now(UTC)
        values = {
            "id": f"ntf_{uuid.uuid4().hex}",
            "user_id": user_id,
            "kind": kind.value,
            "payload": asdict(payload),
            "created_at": moment,
            "read_at": None,
            "dedupe_key": dedupe_key,
        }
        stmt = pg_insert(NotificationRow).values(**values)
        if dedupe_key is not None:
            # Повтор того же события не плодит строк: прежнее уведомление снова непрочитанное и свежее.
            stmt = stmt.on_conflict_do_update(
                index_elements=[NotificationRow.user_id, NotificationRow.dedupe_key],
                index_where=NotificationRow.dedupe_key.is_not(None),
                set_={"payload": values["payload"], "created_at": moment, "read_at": None, "kind": kind.value},
            )
        async with self._sessions.use() as session:
            await session.execute(stmt)

    async def page(self, user_id: str, *, unread_only: bool, window: Window) -> Found[Notification]:
        where = [NotificationRow.user_id == user_id]
        if unread_only:
            where.append(NotificationRow.read_at.is_(None))
        async with self._sessions.use() as session:
            total = (
                await session.execute(select(func.count()).select_from(NotificationRow).where(*where))
            ).scalar_one()
            rows = (
                await session.execute(
                    select(NotificationRow)
                    .where(*where)
                    .order_by(NotificationRow.created_at.desc(), NotificationRow.id.desc())
                    .limit(window.limit)
                    .offset(window.offset)
                )
            ).scalars()
            return Found([_to_entity(r) for r in rows], int(total))

    async def unread_count(self, user_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(NotificationRow)
            .where(NotificationRow.user_id == user_id, NotificationRow.read_at.is_(None))
        )
        async with self._sessions.use() as session:
            return int((await session.execute(stmt)).scalar_one())

    async def mark_read(self, user_id: str, ids: Sequence[str] | None, now: datetime) -> int:
        stmt = update(NotificationRow).where(NotificationRow.user_id == user_id, NotificationRow.read_at.is_(None))
        if ids is not None:
            if not ids:
                return 0
            stmt = stmt.where(NotificationRow.id.in_(list(ids)))
        async with self._sessions.use() as session:
            result = await session.execute(stmt.values(read_at=now).returning(NotificationRow.id))
            return len(result.all())

    async def purge(self, before: datetime) -> int:
        async with self._sessions.use() as session:
            result = await session.execute(
                delete(NotificationRow).where(NotificationRow.created_at < before).returning(NotificationRow.id)
            )
            return len(result.all())
