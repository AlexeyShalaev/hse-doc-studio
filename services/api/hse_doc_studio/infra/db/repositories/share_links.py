"""Ссылки доступа в Postgres: запись, список, отзыв, ссылочные права вошедших и агрегированные переходы."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.access.links import (
    LinkProject,
    LinkRole,
    LinkVisit,
    LinkVisitRecord,
    LinkVisitStats,
    NewShareLinkRecord,
    RevokeReason,
    ShareLink,
    ShareLinkChanges,
    ShareLinkSecrets,
)
from hse_doc_studio.core.listing import Found, Window
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.orm.orgs import OrgRow
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.orm.sharing import ShareLinkGrantRow, ShareLinkRow, ShareLinkVisitRow
from hse_doc_studio.infra.db.session import SessionProvider

_VISIT_KEY = [ShareLinkVisitRow.link_id, ShareLinkVisitRow.visitor_kind, ShareLinkVisitRow.visitor_id]


def share_link_of(row: ShareLinkRow) -> ShareLink:
    return ShareLink(
        id=row.id,
        project_id=row.project_id,
        label=row.label,
        role=LinkRole(row.role),
        show_sources=row.show_sources,
        require_login=row.require_login,
        has_password=row.password_hash is not None,
        token_prefix=row.token_prefix,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        revoke_reason=row.revoke_reason,
        replaced_by=row.replaced_by,
        last_opened_at=row.last_opened_at,
    )


class PostgresShareLinkRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def get(self, link_id: str) -> ShareLink | None:
        async with self._sessions.use() as db:
            row = await db.get(ShareLinkRow, link_id)
            return share_link_of(row) if row is not None else None

    async def get_by_token_hash(self, token_hash: str) -> ShareLink | None:
        async with self._sessions.use() as db:
            row = (await db.execute(select(ShareLinkRow).where(ShareLinkRow.token_hash == token_hash))).scalar()
            return share_link_of(row) if row is not None else None

    async def add(self, record: NewShareLinkRecord) -> None:
        link, secrets = record.link, record.secrets
        async with self._sessions.use() as db:
            db.add(
                ShareLinkRow(
                    id=link.id,
                    project_id=link.project_id,
                    label=link.label,
                    role=link.role.value,
                    show_sources=link.show_sources,
                    require_login=link.require_login,
                    password_hash=secrets.password_hash,
                    token_hash=secrets.token_hash,
                    token_enc=secrets.token_enc,
                    token_prefix=link.token_prefix,
                    created_by=link.created_by,
                    created_at=link.created_at,
                    updated_at=link.updated_at,
                    expires_at=link.expires_at,
                )
            )
            await db.flush()

    async def project(self, project_id: UUID) -> LinkProject | None:
        stmt = (
            select(
                ProjectRow.id,
                ProjectRow.name,
                ProjectRow.owner_user_id,
                ProjectRow.owner_org_id,
                ProjectRow.nda,
                UserRow.name.label("user_name"),
                OrgRow.name.label("org_name"),
            )
            .select_from(ProjectRow)
            .outerjoin(UserRow, UserRow.id == ProjectRow.owner_user_id)
            .outerjoin(OrgRow, OrgRow.id == ProjectRow.owner_org_id)
            .where(ProjectRow.id == project_id, ProjectRow.deleted_at.is_(None))
        )
        async with self._sessions.use() as db:
            row = (await db.execute(stmt)).first()
        if row is None:
            return None
        return LinkProject(
            id=row.id,
            name=row.name,
            owner_user_id=row.owner_user_id,
            owner_org_id=row.owner_org_id,
            owner_name=row.user_name or row.org_name or "",
            nda=row.nda,
        )

    async def user_names(self, user_ids: Sequence[str]) -> dict[str, str]:
        if not user_ids:
            return {}
        async with self._sessions.use() as db:
            rows = await db.execute(select(UserRow.id, UserRow.name).where(UserRow.id.in_(list(set(user_ids)))))
            return {row.id: row.name for row in rows}

    async def secrets_of(self, link_id: str) -> ShareLinkSecrets | None:
        stmt = select(ShareLinkRow.password_hash, ShareLinkRow.token_hash, ShareLinkRow.token_enc).where(
            ShareLinkRow.id == link_id
        )
        async with self._sessions.use() as db:
            row = (await db.execute(stmt)).first()
        if row is None:
            return None
        return ShareLinkSecrets(password_hash=row.password_hash, token_hash=row.token_hash, token_enc=row.token_enc)

    async def list_for_project(
        self, project_id: UUID, *, created_by: str | None, revoked_since: datetime | None
    ) -> list[ShareLink]:
        stmt = select(ShareLinkRow).where(ShareLinkRow.project_id == project_id)
        if created_by is not None:
            stmt = stmt.where(ShareLinkRow.created_by == created_by)
        if revoked_since is None:
            stmt = stmt.where(ShareLinkRow.revoked_at.is_(None))
        else:
            stmt = stmt.where((ShareLinkRow.revoked_at.is_(None)) | (ShareLinkRow.revoked_at >= revoked_since))
        stmt = stmt.order_by(ShareLinkRow.created_at.desc(), ShareLinkRow.id)
        async with self._sessions.use() as db:
            return [share_link_of(row) for row in (await db.execute(stmt)).scalars()]

    async def count_active(self, project_id: UUID, now: datetime) -> int:
        stmt = select(func.count()).where(
            ShareLinkRow.project_id == project_id,
            ShareLinkRow.revoked_at.is_(None),
            (ShareLinkRow.expires_at.is_(None)) | (ShareLinkRow.expires_at > now),
        )
        async with self._sessions.use() as db:
            return int((await db.execute(stmt)).scalar_one())

    async def count_revoked(self, project_id: UUID, *, created_by: str | None, since: datetime) -> int:
        stmt = select(func.count()).where(ShareLinkRow.project_id == project_id, ShareLinkRow.revoked_at >= since)
        if created_by is not None:
            stmt = stmt.where(ShareLinkRow.created_by == created_by)
        async with self._sessions.use() as db:
            return int((await db.execute(stmt)).scalar_one())

    async def update(self, link_id: str, changes: ShareLinkChanges, now: datetime) -> ShareLink | None:
        values: dict[str, object] = {"updated_at": now}
        if changes.label is not None:
            values["label"] = changes.label
        if changes.role is not None:
            values["role"] = changes.role.value
        if changes.show_sources is not None:
            values["show_sources"] = changes.show_sources
        if changes.require_login is not None:
            values["require_login"] = changes.require_login
        if changes.set_password:
            values["password_hash"] = changes.password_hash
        if changes.set_expiry:
            values["expires_at"] = changes.expires_at
        stmt = (
            update(ShareLinkRow)
            .where(ShareLinkRow.id == link_id, ShareLinkRow.revoked_at.is_(None))
            .values(**values)
            .returning(ShareLinkRow)
        )
        async with self._sessions.use() as db:
            row = (await db.execute(stmt)).scalar()
            return share_link_of(row) if row is not None else None

    async def revoke(
        self, link_id: str, *, by: str | None, reason: RevokeReason, now: datetime, replaced_by: str | None = None
    ) -> bool:
        stmt = (
            update(ShareLinkRow)
            .where(ShareLinkRow.id == link_id, ShareLinkRow.revoked_at.is_(None))
            .values(revoked_at=now, revoked_by=by, revoke_reason=reason.value, replaced_by=replaced_by, updated_at=now)
            .returning(ShareLinkRow.id)
        )
        async with self._sessions.use() as db:
            return (await db.execute(stmt)).scalar() is not None

    async def touch_opened(self, link_id: str, now: datetime) -> None:
        async with self._sessions.use() as db:
            await db.execute(update(ShareLinkRow).where(ShareLinkRow.id == link_id).values(last_opened_at=now))

    async def visit_stats(self, link_ids: Sequence[str]) -> dict[str, LinkVisitStats]:
        if not link_ids:
            return {}
        stmt = (
            select(
                ShareLinkVisitRow.link_id,
                func.count().label("visitors"),
                func.coalesce(func.sum(ShareLinkVisitRow.opens), 0).label("opens"),
                func.max(ShareLinkVisitRow.last_at).label("last_at"),
            )
            .where(ShareLinkVisitRow.link_id.in_(list(link_ids)))
            .group_by(ShareLinkVisitRow.link_id)
        )
        async with self._sessions.use() as db:
            rows = (await db.execute(stmt)).all()
        return {
            row.link_id: LinkVisitStats(visitors=int(row.visitors), opens=int(row.opens), last_at=row.last_at)
            for row in rows
        }

    async def visits(self, link_id: str, window: Window) -> Found[LinkVisit]:
        where = ShareLinkVisitRow.link_id == link_id
        stmt = (
            select(ShareLinkVisitRow)
            .where(where)
            .order_by(ShareLinkVisitRow.last_at.desc(), ShareLinkVisitRow.visitor_id)
            .limit(window.limit)
            .offset(window.offset)
        )
        async with self._sessions.use() as db:
            total = int((await db.execute(select(func.count()).where(where))).scalar_one())
            rows = list((await db.execute(stmt)).scalars())
        items = [
            LinkVisit(
                visitor_kind="guest" if row.visitor_kind == "guest" else "user",
                visitor_id=row.visitor_id,
                name=row.visitor_name,
                first_at=row.first_at,
                last_at=row.last_at,
                opens=row.opens,
            )
            for row in rows
        ]
        return Found(items, total)

    async def record_visit(  # noqa: PLR0913 — запись визита несёт всё, что видно в журнале
        self,
        link_id: str,
        visitor_kind: Literal["guest", "user"],
        visitor_id: str,
        visitor_name: str | None,
        ip: str | None,
        now: datetime,
    ) -> LinkVisitRecord:
        key = (
            ShareLinkVisitRow.link_id == link_id,
            ShareLinkVisitRow.visitor_kind == visitor_kind,
            ShareLinkVisitRow.visitor_id == visitor_id,
        )
        async with self._sessions.use() as db:
            previous = (await db.execute(select(ShareLinkVisitRow.last_at).where(*key).with_for_update())).scalar()
            insert = pg_insert(ShareLinkVisitRow).values(
                link_id=link_id,
                visitor_kind=visitor_kind,
                visitor_id=visitor_id,
                visitor_name=visitor_name,
                first_at=now,
                last_at=now,
                opens=1,
                last_ip=ip,
            )
            await db.execute(
                insert.on_conflict_do_update(
                    index_elements=[
                        ShareLinkVisitRow.link_id,
                        ShareLinkVisitRow.visitor_kind,
                        ShareLinkVisitRow.visitor_id,
                    ],
                    set_={
                        "visitor_name": insert.excluded.visitor_name,
                        "last_at": insert.excluded.last_at,
                        "last_ip": insert.excluded.last_ip,
                        "opens": ShareLinkVisitRow.opens + 1,
                    },
                )
            )
        # «Первый вход за сутки» по календарным суткам UTC: журнал аудита не растёт от каждого клика.
        return LinkVisitRecord(
            first_today=previous is None or previous.astimezone(UTC).date() != now.astimezone(UTC).date()
        )

    async def grant_user(self, link_id: str, user_id: str, project_id: UUID, now: datetime) -> None:
        stmt = (
            pg_insert(ShareLinkGrantRow)
            .values(link_id=link_id, user_id=user_id, project_id=project_id, created_at=now)
            .on_conflict_do_nothing()
        )
        async with self._sessions.use() as db:
            await db.execute(stmt)
