"""project_usage в Postgres и сборка сирот: счётчики, давние проекты, GC не трогает проекты с записью."""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.projects.usage import ProjectUsage
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.repositories.identity import SqlUserRepository
from hse_doc_studio.infra.db.repositories.project_usage import PostgresProjectUsageStore
from hse_doc_studio.infra.db.repositories.projects import PostgresProjectLocator
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.persistence.project import JsonProjectRepository
from hse_doc_studio.infra.projects.orphan_gc import OrphanGc
from hse_doc_studio.infra.projects.volume import LocalDiskProjectVolume
from hse_doc_studio.infra.storage.fs import FsObjectStore
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.contract.test_identity_contract import make_user
from tests.factories import make_document, make_project
from tests.fixtures.actors import as_actor

pytestmark = pytest.mark.pg

_ANNA = Actor.user("anna", name="Анна")
_NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


class World:
    def __init__(self, sessions: SessionProvider, tmp_path: Path) -> None:
        self.sessions = sessions
        self.volume = LocalDiskProjectVolume(tmp_path / "projects")
        self.objects = FsObjectStore(tmp_path / "objects", max_object_bytes=10**6)
        self.projects = JsonProjectRepository()
        self.locator = PostgresProjectLocator(sessions, self.volume, self.projects)
        self.store = PostgresProjectUsageStore(sessions)

    async def add_project(self) -> object:
        from dataclasses import replace

        project_id = uuid4()
        folder = self.volume.allocate(project_id)
        self.projects.save(replace(make_project(folder=folder, documents=[make_document()]), id=project_id))
        with as_actor(_ANNA):
            await self.locator.register(folder)
        return project_id

    def gc(self, min_age_h: float = 24) -> OrphanGc:
        return OrphanGc(self.sessions, self.volume, self.objects, timedelta(hours=min_age_h))

    def age(self, folder: Path, hours: float) -> None:
        old = time.time() - hours * 3600
        os.utime(folder, (old, old))


@pytest_asyncio.fixture
async def world(pg_migrated_engine: AsyncEngine, tmp_path: Path) -> World:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    await SqlUserRepository(sessions).add(make_user("anna"))
    return World(sessions, tmp_path)


async def test__store__save_then_increment_never_goes_below_zero(world: World) -> None:
    project_id = await world.add_project()
    assert await world.store.get(project_id) is None  # type: ignore[arg-type]

    await world.store.save(ProjectUsage(project_id, 100, 20, 3, _NOW))  # type: ignore[arg-type]
    await world.store.add_tree(project_id, 50, _NOW)  # type: ignore[arg-type]
    await world.store.add_tree(project_id, -1000, _NOW)  # type: ignore[arg-type]

    assert await world.store.get(project_id) == ProjectUsage(project_id, 0, 20, 3, _NOW)  # type: ignore[arg-type]


async def test__store__add_tree_without_row__creates_it(world: World) -> None:
    project_id = await world.add_project()

    await world.store.add_tree(project_id, 40, _NOW)  # type: ignore[arg-type]

    usage = await world.store.get(project_id)  # type: ignore[arg-type]
    assert usage is not None
    assert usage.bytes_tree == 40


async def test__stale__unmeasured_first_then_oldest_skipping_fresh(world: World) -> None:
    fresh = await world.add_project()
    old = await world.add_project()
    never = await world.add_project()
    await world.store.save(ProjectUsage(fresh, 1, 0, 0, _NOW))  # type: ignore[arg-type]
    await world.store.save(ProjectUsage(old, 1, 0, 0, _NOW - timedelta(hours=3)))  # type: ignore[arg-type]

    ids = await world.store.stale(_NOW - timedelta(hours=1), 10)

    assert ids == [never, old]
    assert await world.store.stale(_NOW - timedelta(hours=1), 1) == [never]


async def test__gc__removes_orphan_folder_and_prefix_but_keeps_projects(world: World) -> None:
    kept = await world.add_project()
    orphan = uuid4()
    orphan_folder = world.volume.allocate(orphan)
    (orphan_folder / "x.tex").write_text("x")
    young = uuid4()
    world.volume.allocate(young)
    stray = world.volume.root / "not-a-project"
    stray.mkdir()
    for folder in (world.volume.path_of(kept), orphan_folder, stray):  # type: ignore[arg-type]
        world.age(folder, 48)
    await world.objects.put(f"artifacts/{orphan}/pdf/d/a.pdf", b"1")
    await world.objects.put(f"artifacts/{kept}/pdf/d/a.pdf", b"1")
    await world.objects.put("artifacts/not-a-uuid/x", b"1")

    report = await world.gc(min_age_h=0.0001).run(now=_NOW + timedelta(days=3650))

    assert set(report.folders) == {orphan, young}
    assert world.volume.exists(kept)  # type: ignore[arg-type]
    assert stray.is_dir()
    assert not orphan_folder.exists()
    keys = {obj.key for obj in await world.objects.list_objects("artifacts/")}
    assert keys == {f"artifacts/{kept}/pdf/d/a.pdf", "artifacts/not-a-uuid/x"}
    assert report.prefixes == [orphan]


async def test__gc__young_orphans_survive_grace_period(world: World) -> None:
    young = uuid4()
    folder = world.volume.allocate(young)
    await world.objects.put(f"artifacts/{young}/pdf/d/a.pdf", b"1")

    report = await world.gc(min_age_h=24).run()

    assert report.folders == []
    assert report.prefixes == []
    assert folder.is_dir()
