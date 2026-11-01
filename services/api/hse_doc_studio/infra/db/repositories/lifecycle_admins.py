"""Postgres: действующие админы установки (адресаты системных предупреждений)."""

from __future__ import annotations

from sqlalchemy import select

from hse_doc_studio.core.identity.entities import UserStatus
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.session import SessionProvider


class SqlAdminDirectory:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def active_admin_ids(self) -> list[str]:
        stmt = select(UserRow.id).where(UserRow.is_instance_admin.is_(True), UserRow.status == UserStatus.active.value)
        async with self._sessions.use() as db:
            return list((await db.execute(stmt)).scalars())
