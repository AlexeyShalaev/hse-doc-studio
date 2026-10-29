from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from hse_doc_studio.core.storage import blob_key
from hse_doc_studio.infra.storage.blobs import ObjectBlobStore
from hse_doc_studio.infra.storage.fs import FsObjectStore
from hse_doc_studio.use_cases.storage.gc_blobs import GcBlobsUC

from tests.fakes.blob_registry import InMemoryBlobRegistry

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
MIN_AGE = timedelta(days=14)


class FixedLive:
    def __init__(self, shas: set[str]) -> None:
        self.shas = shas

    async def live_blobs(self) -> set[str]:
        return self.shas


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class World:
    def __init__(self, tmp_path: Path) -> None:
        self.objects = FsObjectStore(tmp_path / "objects", max_object_bytes=1024 * 1024)
        self.blobs = ObjectBlobStore(self.objects)
        self.registry = InMemoryBlobRegistry()
        self.live = FixedLive(set())

    def uc(self, batch: int = 100) -> GcBlobsUC:
        return GcBlobsUC(self.registry, self.blobs, self.objects, self.live, min_age=MIN_AGE, batch_size=batch)

    async def add(self, data: bytes, *, age: timedelta, registered: bool = True) -> str:
        await self.blobs.put(data)
        if registered:
            await self.registry.record({sha(data): len(data)}, NOW - age)
        return sha(data)


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


async def test__run__unreferenced_longer_than_min_age__removed(world: World) -> None:
    old = await world.add(b"old", age=timedelta(days=15))
    await world.add(b"fresh", age=timedelta(days=1))

    report = await world.uc().run(NOW)

    assert (report.removed, report.freed_bytes) == (1, 3)
    assert await world.objects.head(blob_key(old)) is None
    assert old not in world.registry.blobs
    assert len(world.registry.blobs) == 1


async def test__run__blob_referenced_again__survives(world: World) -> None:
    kept = await world.add(b"data", age=timedelta(days=30))
    await world.registry.touch([kept], NOW - timedelta(days=1))

    await world.uc().run(NOW)

    assert await world.objects.head(blob_key(kept)) is not None


async def test__run__blob_of_unfinished_job__survives_however_old(world: World) -> None:
    pinned = await world.add(b"pinned", age=timedelta(days=90))
    world.live.shas.add(pinned)

    report = await world.uc().run(NOW)

    assert report.removed == 0
    assert await world.objects.head(blob_key(pinned)) is not None


async def test__run__more_than_one_batch__all_removed(world: World) -> None:
    for i in range(5):
        await world.add(f"blob-{i}".encode(), age=timedelta(days=20))

    report = await world.uc().run(NOW)

    assert report.removed == 5
    assert world.registry.blobs == {}


async def test__run__old_object_without_registry_row__removed_registered_kept(world: World) -> None:
    orphan = await world.add(b"old-orphan", age=timedelta(0), registered=False)
    registered = await world.add(b"registered", age=timedelta(0), registered=False)
    later = NOW + timedelta(days=20)
    await world.registry.record({registered: len(b"registered")}, later - timedelta(days=1))

    report = await world.uc().run(later)

    assert report.orphans_removed == 1
    assert await world.objects.head(blob_key(orphan)) is None
    assert await world.objects.head(blob_key(registered)) is not None


async def test__run__young_orphan__kept(world: World) -> None:
    orphan = await world.add(b"young-orphan", age=timedelta(0), registered=False)

    report = await world.uc().run(datetime.now(tz=timezone.utc))

    assert report.orphans_removed == 0
    assert await world.objects.head(blob_key(orphan)) is not None


async def test__run__zero_min_age__collects_nothing(world: World) -> None:
    await world.add(b"x", age=timedelta(days=100))
    uc = GcBlobsUC(world.registry, world.blobs, world.objects, world.live, min_age=timedelta(0))

    assert (await uc.run(NOW)).removed == 0
