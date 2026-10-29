"""Сборка мусора блобов: давно не упомянутые в манифестах и осиротевшие объекты хранилища."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import structlog

from hse_doc_studio.core.storage.keys import is_sha256
from hse_doc_studio.core.storage.manifest import IBlobRegistry, ILiveBlobSource
from hse_doc_studio.core.storage.ports import IBlobStore, IObjectStore

logger = structlog.get_logger()

BLOB_PREFIX = "blobs/"
DEFAULT_MIN_AGE = timedelta(days=14)
DEFAULT_BATCH = 100


@dataclass
class BlobGcReport:
    removed: int = 0
    freed_bytes: int = 0
    orphans_removed: int = 0


class GcBlobsUC:
    """Удаляет блоб, только если на него не ссылались дольше `min_age` и он не нужен незавершённой задаче.

    Возраст защищает и от гонки загрузки: свежезалитый объект ещё не занесён в реестр. Объект без записи в реестре
    (сбой между загрузкой и записью) стирается по тому же сроку давности объекта.
    """

    def __init__(
        self,
        registry: IBlobRegistry,
        blobs: IBlobStore,
        objects: IObjectStore,
        live: ILiveBlobSource,
        *,
        min_age: timedelta = DEFAULT_MIN_AGE,
        batch_size: int = DEFAULT_BATCH,
    ) -> None:
        self._registry = registry
        self._blobs = blobs
        self._objects = objects
        self._live = live
        self._min_age = min_age
        self._batch = batch_size

    async def run(self, now: datetime | None = None) -> BlobGcReport:
        report = BlobGcReport()
        if self._min_age <= timedelta(0):
            return report
        cutoff = (now or datetime.now(tz=timezone.utc)) - self._min_age
        live = await self._live.live_blobs()
        while True:
            reaped = await self._registry.reap(cutoff, self._batch, self._blobs.delete, keep=live)
            if not reaped:
                break
            report.removed += len(reaped)
            report.freed_bytes += sum(blob.size for blob in reaped)
        report.orphans_removed = await self._sweep_orphans(cutoff, live)
        if report.removed or report.orphans_removed:
            logger.info(
                "blobs collected",
                removed=report.removed,
                freed_bytes=report.freed_bytes,
                orphans=report.orphans_removed,
            )
        return report

    async def _sweep_orphans(self, cutoff: datetime, live: set[str]) -> int:
        old = {
            info.key.rsplit("/", 1)[-1]: info
            for info in await self._objects.list_objects(BLOB_PREFIX)
            if info.last_modified < cutoff
        }
        shas = [sha for sha in old if is_sha256(sha) and sha not in live]
        removed = 0
        for start in range(0, len(shas), self._batch):
            batch = shas[start : start + self._batch]
            for sha in set(batch) - await self._registry.known(batch):
                await self._blobs.delete(sha)
                removed += 1
        return removed
