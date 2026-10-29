"""PostgresBlobRegistry: наличие, продление, кэш хешей, удаление по давности под блокировкой."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.storage.manifest import HashCacheEntry
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.blobs import BlobRow, FileHashCacheRow
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.repositories.blobs import PostgresBlobRegistry
from hse_doc_studio.infra.db.session import SessionProvider
from sqlalchemy import delete, func, select

pytestmark = pytest.mark.pg

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)


def sha(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


@pytest.fixture
async def world(pg_migrated_engine):  # type: ignore[no-untyped-def]
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    return sessions, PostgresBlobRegistry(sessions)


async def add_project(sessions: SessionProvider) -> UUID:
    project_id = uuid4()
    async with sessions.use() as session:
        session.add(ProjectRow(id=project_id, name="p", workspace_path=str(project_id), kind="thesis", lang="ru"))
    return project_id


async def test__record_and_touch__known_blobs_found_and_unknown_not(world) -> None:  # type: ignore[no-untyped-def]
    _, registry = world
    await registry.record({sha("a"): 1, sha("b"): 2}, NOW)

    assert await registry.touch([sha("a"), sha("zzz")], NOW + timedelta(days=1)) == {sha("a")}
    assert await registry.known([sha("a"), sha("b"), sha("c")]) == {sha("a"), sha("b")}


async def test__record__again__extends_life_without_changing_creation(world) -> None:  # type: ignore[no-untyped-def]
    sessions, registry = world
    await registry.record({sha("a"): 1}, NOW)
    await registry.record({sha("a"): 1}, NOW + timedelta(days=5))

    async with sessions.use() as session:
        row = (await session.execute(select(BlobRow))).scalar_one()
    assert (row.created_at, row.last_referenced_at) == (NOW, NOW + timedelta(days=5))


async def test__hash_cache__roundtrip_and_update(world) -> None:  # type: ignore[no-untyped-def]
    sessions, registry = world
    project_id = await add_project(sessions)

    await registry.store_hash_cache(project_id, {"a.tex": HashCacheEntry(1, 2, sha("x"))})
    await registry.store_hash_cache(project_id, {"a.tex": HashCacheEntry(3, 4, sha("y"))})

    assert await registry.hash_cache(project_id, ["a.tex", "b.tex"]) == {"a.tex": HashCacheEntry(3, 4, sha("y"))}


async def test__hash_cache__project_removed__rows_cascade(world) -> None:  # type: ignore[no-untyped-def]
    sessions, registry = world
    project_id = await add_project(sessions)
    await registry.store_hash_cache(project_id, {"a.tex": HashCacheEntry(1, 2, sha("x"))})

    async with sessions.use() as session:
        await session.execute(delete(ProjectRow).where(ProjectRow.id == project_id))
        assert (await session.execute(select(func.count()).select_from(FileHashCacheRow))).scalar_one() == 0


async def test__reap__old_unreferenced_removed_keep_and_fresh_survive(world) -> None:  # type: ignore[no-untyped-def]
    _, registry = world
    await registry.record({sha("old"): 3, sha("pinned"): 6}, NOW - timedelta(days=30))
    await registry.record({sha("fresh"): 5}, NOW)
    deleted: list[str] = []

    async def remove(s: str) -> None:
        deleted.append(s)

    reaped = await registry.reap(NOW - timedelta(days=14), 10, remove, keep={sha("pinned")})

    assert [(b.sha256, b.size) for b in reaped] == [(sha("old"), 3)]
    assert deleted == [sha("old")]
    assert await registry.known([sha("old"), sha("pinned"), sha("fresh")]) == {sha("pinned"), sha("fresh")}


async def test__reap__object_delete_fails__row_stays(world) -> None:  # type: ignore[no-untyped-def]
    _, registry = world
    await registry.record({sha("a"): 1, sha("b"): 1}, NOW - timedelta(days=30))

    async def remove(s: str) -> None:
        if s == sha("a"):
            raise OSError("s3 down")

    reaped = await registry.reap(NOW - timedelta(days=14), 10, remove)

    assert [b.sha256 for b in reaped] == [sha("b")]
    assert await registry.known([sha("a"), sha("b")]) == {sha("a")}


async def test__touch__during_reap__waits_and_blob_is_gone_afterwards(world) -> None:  # type: ignore[no-untyped-def]
    _, registry = world
    await registry.record({sha("a"): 1}, NOW - timedelta(days=30))
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_remove(_s: str) -> None:
        started.set()
        await release.wait()

    reaper = asyncio.create_task(registry.reap(NOW - timedelta(days=14), 10, slow_remove))
    await started.wait()
    toucher = asyncio.create_task(registry.touch([sha("a")], NOW))
    await asyncio.sleep(0.2)
    assert not toucher.done()

    release.set()
    await reaper

    assert await toucher == set()
