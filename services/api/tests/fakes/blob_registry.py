"""Реестр блобов в памяти для тестов загрузчика и сборки мусора."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from hse_doc_studio.core.storage.manifest import HashCacheEntry, UnreferencedBlob


@dataclass
class _Blob:
    size: int
    last_referenced_at: datetime


class InMemoryBlobRegistry:
    def __init__(self) -> None:
        self.blobs: dict[str, _Blob] = {}
        self.cache: dict[tuple[UUID, str], HashCacheEntry] = {}

    async def touch(self, shas: Collection[str], now: datetime) -> set[str]:
        found = {sha for sha in shas if sha in self.blobs}
        for sha in found:
            self.blobs[sha].last_referenced_at = now
        return found

    async def record(self, blobs: Mapping[str, int], now: datetime) -> None:
        for sha, size in blobs.items():
            if sha in self.blobs:
                self.blobs[sha].last_referenced_at = now
            else:
                self.blobs[sha] = _Blob(size, now)

    async def known(self, shas: Collection[str]) -> set[str]:
        return {sha for sha in shas if sha in self.blobs}

    async def hash_cache(self, project_id: UUID, paths: Collection[str]) -> dict[str, HashCacheEntry]:
        return {path: self.cache[project_id, path] for path in paths if (project_id, path) in self.cache}

    async def store_hash_cache(self, project_id: UUID, entries: Mapping[str, HashCacheEntry]) -> None:
        for path, entry in entries.items():
            self.cache[project_id, path] = entry

    async def reap(
        self,
        older_than: datetime,
        limit: int,
        remove: Callable[[str], Awaitable[None]],
        *,
        keep: Collection[str] = (),
    ) -> list[UnreferencedBlob]:
        old = sorted(
            (sha for sha, blob in self.blobs.items() if blob.last_referenced_at < older_than and sha not in keep),
            key=lambda sha: (self.blobs[sha].last_referenced_at, sha),
        )[:limit]
        removed = []
        for sha in old:
            await remove(sha)
            removed.append(UnreferencedBlob(sha, self.blobs.pop(sha).size))
        return removed
