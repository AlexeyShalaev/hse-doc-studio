"""Занятое место по записям базы (blobs, projects), без перечисления бакета."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import BigInteger, Select, String, cast, func, literal, null, select, union_all

from hse_doc_studio.core.listing import Paged
from hse_doc_studio.core.storage.usage import (
    OwnerUsage,
    StorageOwner,
    StorageOwnerKind,
    StorageOwnerQuery,
    StorageUsage,
)
from hse_doc_studio.infra.db.orm.blobs import BlobRow
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.orm.orgs import OrgRow
from hse_doc_studio.infra.db.orm.project_usage import ProjectUsageRow
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.search import matches_any, ordered
from hse_doc_studio.infra.db.session import SessionProvider

# Крупнейшие владельцы в сводке места: только для KPI, полный список отдаёт `list_owners`.
TOP_OWNERS = 5


def _owner_branch(kind: StorageOwnerKind, q: str | None) -> Select[*tuple[Any, ...]]:
    """Владельцы одного вида с числом живых проектов и местом по последнему измерению каждого проекта."""
    used = ProjectUsageRow.bytes_tree + ProjectUsageRow.bytes_git + ProjectUsageRow.bytes_s3
    if kind is StorageOwnerKind.user:
        owner_id, name, email = UserRow.id, UserRow.name, UserRow.email
        searched: list[Any] = [UserRow.name, UserRow.email]
        link = UserRow.id == ProjectRow.owner_user_id
        owner: Any = UserRow
    else:
        owner_id, name, email = OrgRow.id, OrgRow.name, cast(null(), String)
        searched = [OrgRow.name, OrgRow.slug]
        link = OrgRow.id == ProjectRow.owner_org_id
        owner = OrgRow
    stmt = (
        select(
            literal(kind.value, String).label("kind"),
            owner_id.label("id"),
            name.label("name"),
            email.label("email"),
            func.count(ProjectRow.id).label("projects"),
            cast(func.coalesce(func.sum(used), 0), BigInteger).label("bytes"),
        )
        .select_from(ProjectRow)
        .join(owner, link)
        .outerjoin(ProjectUsageRow, ProjectUsageRow.project_id == ProjectRow.id)
        .where(ProjectRow.deleted_at.is_(None))
        .group_by(owner_id)
    )
    if q:
        stmt = stmt.where(matches_any(q, searched))
    return stmt


class SqlStorageUsageReader:
    def __init__(self, sessions: SessionProvider, volume_root: Path | None = None) -> None:
        self._sessions = sessions
        self._volume_root = volume_root

    async def read(self, now: datetime) -> StorageUsage:
        async with self._sessions.use() as session:
            blob_count, blob_bytes = (
                await session.execute(select(func.count(), func.coalesce(func.sum(BlobRow.size), 0)))
            ).one()
            projects = (await session.execute(select(func.count()).where(ProjectRow.deleted_at.is_(None)))).scalar_one()
            deleted = (
                await session.execute(select(func.count()).where(ProjectRow.deleted_at.is_not(None)))
            ).scalar_one()
            owners = (
                await session.execute(
                    select(UserRow.id, UserRow.name, func.count().label("n"))
                    .join(ProjectRow, ProjectRow.owner_user_id == UserRow.id)
                    .where(ProjectRow.deleted_at.is_(None))
                    .group_by(UserRow.id, UserRow.name)
                    .order_by(func.count().desc(), UserRow.name)
                    .limit(TOP_OWNERS)
                )
            ).all()
        total, free = self._volume()
        return StorageUsage(
            blob_count=int(blob_count),
            blob_bytes=int(blob_bytes),
            projects=int(projects),
            deleted_projects=int(deleted),
            top_owners=tuple(OwnerUsage(owner_id=o[0], owner_name=o[1], projects=int(o[2])) for o in owners),
            volume_total_bytes=total,
            volume_free_bytes=free,
            computed_at=now,
        )

    def _volume(self) -> tuple[int | None, int | None]:
        if self._volume_root is None:
            return None, None
        try:
            usage = shutil.disk_usage(self._volume_root)
        except OSError:
            return None, None
        return usage.total, usage.free

    async def list_owners(self, query: StorageOwnerQuery) -> Paged[StorageOwner]:
        kinds = [k for k in StorageOwnerKind if not query.kinds or k in query.kinds]
        owners = union_all(*(_owner_branch(k, query.q) for k in kinds)).subquery("owners")
        keys: dict[str, list[Any]] = {
            "projects": [owners.c.projects],
            "bytes": [owners.c.bytes],
            "name": [func.lower(owners.c.name)],
        }
        stmt = (
            select(owners)
            .order_by(*ordered(query.sort, keys, owners.c.id))
            .limit(query.window.limit)
            .offset(query.window.offset)
        )
        async with self._sessions.use() as session:
            total = (await session.execute(select(func.count()).select_from(owners))).scalar_one()
            rows = (await session.execute(stmt)).all()
        return Paged(
            items=tuple(
                StorageOwner(
                    kind=StorageOwnerKind(row.kind),
                    id=row.id,
                    name=row.name,
                    email=row.email,
                    projects=int(row.projects),
                    bytes=int(row.bytes),
                )
                for row in rows
            ),
            total=int(total),
        )
