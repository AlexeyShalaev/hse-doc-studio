"""Занятое место по записям базы (blobs, projects), без перечисления бакета."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select

from hse_doc_studio.core.storage.usage import OwnerUsage, StorageUsage
from hse_doc_studio.infra.db.orm.blobs import BlobRow
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.session import SessionProvider

TOP_OWNERS = 10


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
