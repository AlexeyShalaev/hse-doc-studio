"""Манифест файлов проекта: хеширование с кэшем и догрузка недостающих блобов."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, cast
from uuid import UUID

from hse_doc_studio.core.jobs.files import ManifestFile, validate_relative_posix
from hse_doc_studio.core.projects.volume import IProjectVolume, UnsafePathError
from hse_doc_studio.core.storage.errors import ChecksumMismatchError
from hse_doc_studio.core.storage.hashing import measure
from hse_doc_studio.core.storage.manifest import (
    RACY_WINDOW_NS,
    HashCacheEntry,
    IBlobRegistry,
    ManifestFileChangedError,
    ManifestFileMissingError,
    ManifestFileTooLargeError,
    ManifestLimits,
    ManifestTooLargeError,
    ManifestUnsafePathError,
)
from hse_doc_studio.core.storage.ports import IBlobStore

_UPLOAD_CONCURRENCY = 4


class ManifestBlobUploader:
    """Все чтения идут через `IProjectVolume.safe_open`: симлинк и выход за папку отвергаются.

    Кэш хеша верит паре (mtime_ns, size) только для файлов, которые к моменту хеширования не менялись дольше
    `RACY_WINDOW_NS`: файл, изменённый в ту же долю секунды после хеширования, в кэш не попадает. После git checkout
    mtime обновляется вместе с содержимым, поэтому такой файл просто хешируется заново.
    """

    def __init__(
        self,
        volume: IProjectVolume,
        registry: IBlobRegistry,
        blobs: IBlobStore,
        *,
        clock_ns: Callable[[], int] = time.time_ns,
    ) -> None:
        self._volume = volume
        self._registry = registry
        self._blobs = blobs
        self._clock_ns = clock_ns

    async def ensure(
        self, project_id: UUID, folder: Path, paths: Sequence[str], limits: ManifestLimits | None = None
    ) -> list[ManifestFile]:
        limits = limits or ManifestLimits()
        unique = list(dict.fromkeys(paths))
        stats = await asyncio.to_thread(self._stat_all, folder, unique, limits)
        cache = await self._registry.hash_cache(project_id, unique)
        hashed: dict[str, HashCacheEntry] = {}
        for path in unique:
            mtime_ns, size = stats[path]
            entry = cache.get(path)
            if entry is not None and entry.mtime_ns == mtime_ns and entry.size == size:
                hashed[path] = entry
            else:
                hashed[path] = await asyncio.to_thread(self._hash, folder, path, mtime_ns, size)
        fresh = {path: entry for path, entry in hashed.items() if cache.get(path) != entry}

        now = datetime.now(tz=timezone.utc)
        by_sha = {entry.sha256: (path, entry.size) for path, entry in hashed.items()}
        present = await self._registry.touch(by_sha, now)
        gate = asyncio.Semaphore(_UPLOAD_CONCURRENCY)

        async def upload(sha: str) -> None:
            path, size = by_sha[sha]
            async with gate:
                await self._upload(folder, path, sha, size)

        missing = sorted(set(by_sha) - present)
        await asyncio.gather(*(upload(sha) for sha in missing))
        if missing:
            await self._registry.record({sha: by_sha[sha][1] for sha in missing}, now)
        cacheable = {path: entry for path, entry in fresh.items() if self._stable(entry.mtime_ns)}
        if cacheable:
            await self._registry.store_hash_cache(project_id, cacheable)
        return [ManifestFile(path=path, sha256=hashed[path].sha256, size=hashed[path].size) for path in unique]

    def _stable(self, mtime_ns: int) -> bool:
        return self._clock_ns() - mtime_ns > RACY_WINDOW_NS

    def _stat_all(self, folder: Path, paths: Sequence[str], limits: ManifestLimits) -> dict[str, tuple[int, int]]:
        stats: dict[str, tuple[int, int]] = {}
        total = 0
        for path in paths:
            with self._open(folder, path) as handle:
                info = os.fstat(handle.fileno())
            if info.st_size > limits.max_file_bytes:
                raise ManifestFileTooLargeError(path, info.st_size, limits.max_file_bytes)
            total += info.st_size
            if total > limits.max_job_bytes:
                raise ManifestTooLargeError(total, limits.max_job_bytes)
            stats[path] = (info.st_mtime_ns, info.st_size)
        return stats

    def _hash(self, folder: Path, path: str, mtime_ns: int, size: int) -> HashCacheEntry:
        with self._open(folder, path) as handle:
            actual_size, sha = measure(handle)
        if actual_size != size:
            raise ManifestFileChangedError(path)
        return HashCacheEntry(mtime_ns=mtime_ns, size=size, sha256=sha)

    async def _upload(self, folder: Path, path: str, sha: str, size: int) -> None:
        handle = await asyncio.to_thread(self._open, folder, path)
        try:
            info = await self._blobs.put(handle, sha256=sha)
        except ChecksumMismatchError as exc:
            raise ManifestFileChangedError(path) from exc
        finally:
            handle.close()
        if info.size != size:
            raise ManifestFileChangedError(path)

    def _open(self, folder: Path, path: str) -> BinaryIO:
        try:
            validate_relative_posix(path)
            return cast(BinaryIO, self._volume.safe_open(folder, path))
        except (ValueError, UnsafePathError) as exc:
            raise ManifestUnsafePathError(path) from exc
        except FileNotFoundError as exc:
            raise ManifestFileMissingError(path) from exc
