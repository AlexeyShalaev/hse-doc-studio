"""Реестр блобов в Postgres: наличие, давность ссылок и кэш хешей файлов."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection, Iterable, Mapping
from datetime import datetime
from typing import TypeVar
from uuid import UUID

import structlog
from sqlalchemy import String, all_, delete, literal, select, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.storage.manifest import HashCacheEntry, UnreferencedBlob
from hse_doc_studio.infra.db.orm.blobs import BlobRow, FileHashCacheRow
from hse_doc_studio.infra.db.session import SessionProvider

# Параметров на запрос у asyncpg не больше 32767: большие наборы идут пачками.
_CHUNK = 5000
logger = structlog.get_logger()
_T = TypeVar("_T")


def _chunks(items: Iterable[_T]) -> Iterable[list[_T]]:
    batch: list[_T] = []
    for item in items:
        batch.append(item)
        if len(batch) == _CHUNK:
            yield batch
            batch = []
    if batch:
        yield batch


class PostgresBlobRegistry:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def touch(self, shas: Collection[str], now: datetime) -> set[str]:
        found: set[str] = set()
        async with self._sessions.use() as session:
            for batch in _chunks(sorted(set(shas))):
                stmt = (
                    update(BlobRow)
                    .where(BlobRow.sha256.in_(batch))
                    .values(last_referenced_at=now)
                    .returning(BlobRow.sha256)
                )
                found.update((await session.execute(stmt)).scalars())
        return found

    async def record(self, blobs: Mapping[str, int], now: datetime) -> None:
        async with self._sessions.use() as session:
            for batch in _chunks(sorted(blobs)):
                stmt = pg_insert(BlobRow).values(
                    [{"sha256": sha, "size": blobs[sha], "created_at": now, "last_referenced_at": now} for sha in batch]
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=[BlobRow.sha256], set_={"last_referenced_at": stmt.excluded.last_referenced_at}
                )
                await session.execute(stmt)

    async def known(self, shas: Collection[str]) -> set[str]:
        found: set[str] = set()
        async with self._sessions.use() as session:
            for batch in _chunks(sorted(set(shas))):
                found.update((await session.execute(select(BlobRow.sha256).where(BlobRow.sha256.in_(batch)))).scalars())
        return found

    async def forget(self, shas: Collection[str]) -> None:
        async with self._sessions.use() as session:
            for batch in _chunks(sorted(set(shas))):
                await session.execute(delete(BlobRow).where(BlobRow.sha256.in_(batch)))

    async def hash_cache(self, project_id: UUID, paths: Collection[str]) -> dict[str, HashCacheEntry]:
        found: dict[str, HashCacheEntry] = {}
        async with self._sessions.use() as session:
            for batch in _chunks(sorted(set(paths))):
                stmt = select(FileHashCacheRow).where(
                    FileHashCacheRow.project_id == project_id, FileHashCacheRow.path.in_(batch)
                )
                for row in (await session.execute(stmt)).scalars():
                    found[row.path] = HashCacheEntry(mtime_ns=row.mtime_ns, size=row.size, sha256=row.sha256)
        return found

    async def store_hash_cache(self, project_id: UUID, entries: Mapping[str, HashCacheEntry]) -> None:
        async with self._sessions.use() as session:
            for batch in _chunks(sorted(entries)):
                stmt = pg_insert(FileHashCacheRow).values(
                    [
                        {
                            "project_id": project_id,
                            "path": path,
                            "mtime_ns": entries[path].mtime_ns,
                            "size": entries[path].size,
                            "sha256": entries[path].sha256,
                        }
                        for path in batch
                    ]
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=[FileHashCacheRow.project_id, FileHashCacheRow.path],
                    set_={
                        "mtime_ns": stmt.excluded.mtime_ns,
                        "size": stmt.excluded.size,
                        "sha256": stmt.excluded.sha256,
                    },
                )
                await session.execute(stmt)

    async def reap(
        self,
        older_than: datetime,
        limit: int,
        remove: Callable[[str], Awaitable[None]],
        *,
        keep: Collection[str] = (),
    ) -> list[UnreferencedBlob]:
        stmt = (
            select(BlobRow.sha256, BlobRow.size)
            .where(BlobRow.last_referenced_at < older_than)
            .order_by(BlobRow.last_referenced_at, BlobRow.sha256)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        if keep:
            # Одним массивом, а не по параметру на блоб: живых хешей в очереди может быть больше лимита asyncpg.
            stmt = stmt.where(BlobRow.sha256 != all_(literal(sorted(set(keep)), ARRAY(String))))
        removed: list[UnreferencedBlob] = []
        async with self._sessions.use() as session:
            for sha, size in (await session.execute(stmt)).all():
                try:
                    await remove(sha)
                except Exception:  # noqa: BLE001 — запись остаётся, следующий проход повторит
                    logger.warning("blob delete failed", sha256=sha, exc_info=True)
                    continue
                removed.append(UnreferencedBlob(sha256=sha, size=size))
            if removed:
                await session.execute(delete(BlobRow).where(BlobRow.sha256.in_([blob.sha256 for blob in removed])))
        return removed
