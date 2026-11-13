"""Хранилище для напоминаний о сроке контрольной точки (docs/design/signing-route.md, 16.7) в Postgres.

Сроки берутся из копии в каталоге проектов (`projects.deadlines`, только точки версии шаблона проекта с названием),
сборки пакетов из записей сдачи, а «уже напомнили» из уведомлений с ключом повтора: строку уведомления пишет тот
же проход в той же транзакции.
"""

from __future__ import annotations

import hashlib
from collections.abc import Collection
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select

from hse_doc_studio.core.checkpoint_reminders import DueCheckpoint, ReminderRecipient
from hse_doc_studio.core.signatures.plan import AUTHOR_PERSONA
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.orm.invitations import NotificationRow
from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow, ProjectRow
from hse_doc_studio.infra.db.orm.submission import SubmissionRow
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.projects.catalog_sync import read_catalog_deadlines

_ACTIVE = "active"


def _lock_id(key: str) -> int:
    """Ключ повтора как bigint для `pg_advisory_xact_lock`."""
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big", signed=True)


class PostgresCheckpointReminderStore:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def due(self, *, now: datetime, until: datetime) -> list[DueCheckpoint]:
        stmt = select(ProjectRow.id, ProjectRow.name, ProjectRow.deadlines).where(
            ProjectRow.deadlines.is_not(None), ProjectRow.deleted_at.is_(None), ProjectRow.archived_at.is_(None)
        )
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).all()
        found: list[DueCheckpoint] = []
        for project_id, project_name, raw in rows:
            deadlines, names = read_catalog_deadlines(raw)
            for profile_id, deadline in sorted(deadlines.items()):
                if now < deadline <= until:
                    found.append(
                        DueCheckpoint(project_id, project_name, profile_id, deadline, names.get(profile_id, {}))
                    )
        return found

    async def lock(self, key: str) -> None:
        async with self._sessions.use() as session:
            await session.execute(select(func.pg_advisory_xact_lock(_lock_id(key))))

    async def built(self, project_id: UUID, profile_id: str, *, since: datetime) -> list[datetime]:
        stmt = select(SubmissionRow.created_at).where(
            SubmissionRow.project_id == project_id,
            SubmissionRow.profile_id == profile_id,
            SubmissionRow.created_at >= since,
        )
        async with self._sessions.use() as session:
            return list((await session.execute(stmt)).scalars())

    async def recipients(self, project_id: UUID) -> list[ReminderRecipient]:
        owner_stmt = (
            select(UserRow.id, UserRow.locale)
            .join(ProjectRow, ProjectRow.owner_user_id == UserRow.id)
            .where(ProjectRow.id == project_id, UserRow.status == _ACTIVE)
        )
        members_stmt = (
            select(UserRow.id, UserRow.locale)
            .join(ProjectMemberRow, ProjectMemberRow.principal_id == UserRow.id)
            .where(
                ProjectMemberRow.project_id == project_id,
                ProjectMemberRow.principal_kind == "user",
                ProjectMemberRow.persona == AUTHOR_PERSONA,
                UserRow.status == _ACTIVE,
            )
            .order_by(ProjectMemberRow.created_at, ProjectMemberRow.principal_id)
        )
        async with self._sessions.use() as session:
            rows = [*(await session.execute(owner_stmt)).all(), *(await session.execute(members_stmt)).all()]
        people: dict[str, ReminderRecipient] = {}
        for user_id, locale in rows:
            people.setdefault(user_id, ReminderRecipient(user_id, locale))
        return list(people.values())

    async def reminded(self, user_ids: Collection[str], key: str) -> set[str]:
        if not user_ids:
            return set()
        stmt = select(NotificationRow.user_id).where(
            NotificationRow.dedupe_key == key, NotificationRow.user_id.in_(list(user_ids))
        )
        async with self._sessions.use() as session:
            return set((await session.execute(stmt)).scalars())
