"""Имена людей и проектов для строк журнала писем (docs/design/mail-log.md, 6.2): одна выборка на страницу."""

from __future__ import annotations

import uuid
from collections.abc import Collection

from sqlalchemy import select

from hse_doc_studio.core.mail.ports import MailPerson
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.session import SessionProvider


def _uuids(values: Collection[str]) -> dict[uuid.UUID, str]:
    found: dict[uuid.UUID, str] = {}
    for value in values:
        try:
            found[uuid.UUID(value)] = value
        except ValueError:
            continue
    return found


class SqlMailLogNames:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def people(self, user_ids: Collection[str]) -> dict[str, MailPerson]:
        ids = list(set(user_ids))
        if not ids:
            return {}
        stmt = select(UserRow.id, UserRow.name, UserRow.email).where(UserRow.id.in_(ids))
        async with self._sessions.use() as db:
            rows = (await db.execute(stmt)).all()
        return {row.id: MailPerson(id=row.id, name=row.name, email=row.email) for row in rows}

    async def projects(self, project_ids: Collection[str]) -> dict[str, str]:
        ids = _uuids(project_ids)
        if not ids:
            return {}
        # Проект в корзине ещё есть: его название показывается; удалённого насовсем в ответе нет.
        stmt = select(ProjectRow.id, ProjectRow.name).where(ProjectRow.id.in_(list(ids)))
        async with self._sessions.use() as db:
            rows = (await db.execute(stmt)).all()
        return {ids[row.id]: row.name for row in rows if row.id in ids}
