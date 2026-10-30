"""Строки пользователей и проектов в Postgres для тестов маршрута задач и личных раннеров."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.session import SessionProvider

_NOW = datetime(2026, 10, 30, tzinfo=UTC)


async def seed_user(sessions: SessionProvider, user_id: str | None = None, *, status: str = "active") -> str:
    uid = user_id or str(uuid4())
    async with sessions.use() as session:
        session.add(
            UserRow(
                id=uid,
                email=f"{uid}@example.org",
                email_normalized=f"{uid}@example.org",
                name=f"user {uid[:6]}",
                status=status,
                created_at=_NOW,
            )
        )
        await session.flush()
    return uid


async def seed_project(
    sessions: SessionProvider,
    *,
    owner_user_id: str | None,
    project_id: UUID | None = None,
    build_runners: str = "shared",
    deleted: bool = False,
) -> UUID:
    pid = project_id or uuid4()
    async with sessions.use() as session:
        session.add(
            ProjectRow(
                id=pid,
                name="p",
                owner_user_id=owner_user_id,
                workspace_path=str(pid),
                kind="thesis",
                lang="ru",
                build_runners=build_runners,
                deleted_at=_NOW if deleted else None,
            )
        )
        await session.flush()
    return pid
