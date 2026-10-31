"""Гостевые сессии по ссылкам в Postgres: cookie `hse_guest`, имя гостя и открытые в сессии ссылки."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.access.links import GuestLink, GuestSession
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.orm.sharing import GuestSessionLinkRow, GuestSessionRow, ShareLinkRow
from hse_doc_studio.infra.db.repositories.share_links import share_link_of
from hse_doc_studio.infra.db.session import SessionProvider


def _session_of(row: GuestSessionRow) -> GuestSession:
    return GuestSession(
        id=row.id,
        name=row.name,
        created_at=row.created_at,
        last_seen_at=row.last_seen_at,
        expires_at=row.expires_at,
        csrf_token=row.csrf_token,
    )


class PostgresGuestSessionRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def get_by_secret_hash(self, secret_hash: str, now: datetime) -> GuestSession | None:
        stmt = select(GuestSessionRow).where(
            GuestSessionRow.secret_hash == secret_hash, GuestSessionRow.expires_at > now
        )
        async with self._sessions.use() as db:
            row = (await db.execute(stmt)).scalar()
            return _session_of(row) if row is not None else None

    async def create(self, session: GuestSession, secret_hash: str, ip: str | None, user_agent: str) -> None:
        async with self._sessions.use() as db:
            db.add(
                GuestSessionRow(
                    id=session.id,
                    secret_hash=secret_hash,
                    name=session.name,
                    created_at=session.created_at,
                    last_seen_at=session.last_seen_at,
                    expires_at=session.expires_at,
                    ip=ip,
                    user_agent=user_agent[:512],
                    csrf_token=session.csrf_token,
                )
            )
            await db.flush()

    async def touch(self, session_id: str, now: datetime, expires_at: datetime) -> None:
        stmt = (
            update(GuestSessionRow)
            .where(GuestSessionRow.id == session_id)
            .values(last_seen_at=now, expires_at=expires_at)
        )
        async with self._sessions.use() as db:
            await db.execute(stmt)

    async def rename(self, session_id: str, name: str | None) -> None:
        async with self._sessions.use() as db:
            await db.execute(update(GuestSessionRow).where(GuestSessionRow.id == session_id).values(name=name))

    async def attach_link(self, session_id: str, link_id: str, project_id: UUID, now: datetime) -> None:
        async with self._sessions.use() as db:
            # На проект в сессии одна ссылка: новая ссылка того же проекта заменяет прежнюю.
            await db.execute(
                delete(GuestSessionLinkRow).where(
                    GuestSessionLinkRow.session_id == session_id, GuestSessionLinkRow.project_id == project_id
                )
            )
            await db.execute(
                pg_insert(GuestSessionLinkRow)
                .values(session_id=session_id, link_id=link_id, project_id=project_id, opened_at=now)
                .on_conflict_do_nothing()
            )

    async def links_of(self, session_id: str) -> list[GuestLink]:
        stmt = (
            select(ShareLinkRow, ProjectRow.name)
            .join(GuestSessionLinkRow, GuestSessionLinkRow.link_id == ShareLinkRow.id)
            .join(ProjectRow, ProjectRow.id == ShareLinkRow.project_id)
            .where(GuestSessionLinkRow.session_id == session_id, ProjectRow.deleted_at.is_(None))
            .order_by(GuestSessionLinkRow.opened_at.desc())
        )
        async with self._sessions.use() as db:
            rows = (await db.execute(stmt)).all()
        return [GuestLink(link=share_link_of(link), project_name=name) for link, name in rows]

    async def had_link_for(self, session_id: str, project_id: UUID) -> bool:
        stmt = select(GuestSessionLinkRow.link_id).where(
            GuestSessionLinkRow.session_id == session_id, GuestSessionLinkRow.project_id == project_id
        )
        async with self._sessions.use() as db:
            return (await db.execute(stmt)).first() is not None

    async def detach_project(self, session_id: str, project_id: UUID) -> None:
        async with self._sessions.use() as db:
            await db.execute(
                delete(GuestSessionLinkRow).where(
                    GuestSessionLinkRow.session_id == session_id, GuestSessionLinkRow.project_id == project_id
                )
            )

    async def delete(self, session_id: str) -> None:
        async with self._sessions.use() as db:
            await db.execute(delete(GuestSessionRow).where(GuestSessionRow.id == session_id))

    async def purge_expired(self, now: datetime) -> int:
        stmt = delete(GuestSessionRow).where(GuestSessionRow.expires_at <= now).returning(GuestSessionRow.id)
        async with self._sessions.use() as db:
            return len((await db.execute(stmt)).all())
