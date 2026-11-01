"""Серверный локатор проектов на Postgres: видимость, изоляция акторов, том и копия name/kind/lang."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from hse_doc_studio.core.access.context import ActorRequired
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import Lang, PersonRole, ProjectKind
from hse_doc_studio.core.projects.locator import ProjectAlreadyRegisteredError
from hse_doc_studio.core.projects.volume import UnsafePathError
from hse_doc_studio.core.value_objects import Person
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow, ProjectRow
from hse_doc_studio.infra.db.repositories.identity import SqlUserRepository
from hse_doc_studio.infra.db.repositories.projects import PostgresProjectLocator
from hse_doc_studio.infra.db.session import SessionProvider, live_ambient
from hse_doc_studio.infra.persistence.project import JsonProjectRepository
from hse_doc_studio.infra.projects.catalog_sync import (
    MirroringProjectRepository,
    ProjectCatalogMirror,
    ProjectCatalogReconciler,
)
from hse_doc_studio.infra.projects.volume import LocalDiskProjectVolume
from sqlalchemy import select

from tests.contract.test_identity_contract import make_user
from tests.factories import make_project
from tests.fixtures.actors import as_actor

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg


@dataclass
class World:
    sessions: SessionProvider
    volume: LocalDiskProjectVolume
    repo: JsonProjectRepository
    locator: PostgresProjectLocator
    owner: Actor
    stranger: Actor

    def make(self, name: str = "Alpha") -> Project:
        project_id = uuid4()
        folder = self.volume.allocate(project_id)
        project = replace(make_project(folder=folder, name=name), id=project_id)
        self.repo.save(project)
        return project

    async def add(self, name: str = "Alpha", *, actor: Actor | None = None) -> Project:
        project = self.make(name)
        with as_actor(actor or self.owner):
            await self.locator.register(project.folder)
        return project


@pytest_asyncio.fixture
async def world(pg_migrated_engine: AsyncEngine, tmp_path: Path) -> World:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    users = SqlUserRepository(sessions)
    await users.add(make_user("user-a"))
    await users.add(make_user("user-b"))
    volume = LocalDiskProjectVolume(tmp_path / "projects")
    repo = JsonProjectRepository()
    return World(
        sessions,
        volume,
        repo,
        PostgresProjectLocator(sessions, volume, repo),
        Actor.user("user-a"),
        Actor.user("user-b"),
    )


async def _row(world: World, project_id: UUID) -> ProjectRow:
    async with world.sessions.use() as session:
        row = (await session.execute(select(ProjectRow).where(ProjectRow.id == project_id))).scalar_one()
        session.expunge(row)
        return row


async def test__register__known_folder__found_by_id(world: World) -> None:
    project = await world.add()

    assert await world.locator.folder_of(project.id) == project.folder
    found = await world.locator.locate(project.id)
    assert found is not None
    assert found[0] == project.folder
    assert found[1].id == project.id


async def test__register__creates_owner_member(world: World) -> None:
    project = await world.add()

    async with world.sessions.use() as session:
        members = (await session.execute(select(ProjectMemberRow))).scalars().all()
    assert [(m.project_id, m.principal_id, m.role) for m in members] == [(project.id, "user-a", "owner")]


async def test__register__without_actor__actor_required(world: World) -> None:
    project = world.make()

    with as_actor(None), pytest.raises(ActorRequired):
        await world.locator.register(project.folder)


async def test__register__folder_outside_volume__rejected(world: World, tmp_path: Path) -> None:
    with as_actor(world.owner), pytest.raises(UnsafePathError):
        await world.locator.register(tmp_path / str(uuid4()))


async def test__register__twice_by_owner__single_row(world: World) -> None:
    project = await world.add()
    with as_actor(world.owner):
        await world.locator.register(project.folder)

    assert await world.locator.list_all() == [project.folder]


async def test__register__foreign_project__refused(world: World) -> None:
    project = await world.add()

    with as_actor(world.stranger), pytest.raises(ProjectAlreadyRegisteredError):
        await world.locator.register(project.folder)
    assert await world.locator.list_visible(world.stranger) == []


async def test__list_visible__two_actors__each_sees_only_own(world: World) -> None:
    mine = await world.add("Mine", actor=world.owner)
    theirs = await world.add("Theirs", actor=world.stranger)

    assert await world.locator.list_visible(world.owner) == [mine.folder]
    assert await world.locator.list_visible(world.stranger) == [theirs.folder]
    assert await world.locator.list_all() == [mine.folder, theirs.folder]


async def test__list_visible__member_sees_shared_project(world: World) -> None:
    project = await world.add()
    async with world.sessions.use() as session:
        session.add(
            ProjectMemberRow(project_id=project.id, principal_kind="user", principal_id="user-b", role="reader")
        )

    assert await world.locator.list_visible(world.stranger) == [project.folder]


async def test__list_visible__no_actor__actor_required(world: World) -> None:
    with pytest.raises(ActorRequired):
        await world.locator.list_visible(None)


async def test__list_visible__guest_and_local__nothing(world: World) -> None:
    await world.add()

    assert await world.locator.list_visible(Actor.guest("link-1")) == []
    assert await world.locator.list_visible(Actor.local()) == []


async def test__list_visible__keeps_registration_order(world: World) -> None:
    folders = [(await world.add(name)).folder for name in ("c", "a", "b")]

    assert await world.locator.list_visible(world.owner) == folders


async def test__unregister__soft_deletes_and_hides(world: World) -> None:
    project = await world.add()

    await world.locator.unregister(project.folder)

    assert await world.locator.folder_of(project.id) is None
    assert await world.locator.locate(project.id) is None
    assert await world.locator.list_visible(world.owner) == []
    assert (await _row(world, project.id)).deleted_at is not None


async def test__folder_of__unknown_id__none(world: World) -> None:
    await world.add()

    assert await world.locator.folder_of(uuid4()) is None


async def test__locate__row_without_folder__none_and_does_not_raise(world: World) -> None:
    project = await world.add()
    world.volume.remove(project.id)

    assert await world.locator.locate(project.id) is None
    assert await world.locator.list_visible(world.owner) == [project.folder]


async def test__mirror__changed_name__row_updated_once(world: World) -> None:
    project = await world.add("Before")
    mirror = ProjectCatalogMirror(world.sessions)

    assert await mirror.mirror(project.id, replace(project, name="After", lang=Lang.en, kind=ProjectKind.project))
    assert not await mirror.mirror(project.id, replace(project, name="After", lang=Lang.en, kind=ProjectKind.project))

    row = await _row(world, project.id)
    assert (row.name, row.lang, row.kind) == ("After", "en", "project")


async def test__mirror__list_fields_pinned_archive_supervisor_and_edit_time(world: World) -> None:
    project = await world.add("Alpha")
    mirror = ProjectCatalogMirror(world.sessions)
    edited = replace(
        project,
        pinned=True,
        archived=True,
        supervisor=Person(name="Сидоров И. И.", role=PersonRole.university),
        updated_at=datetime(2026, 10, 30, 12, 0, tzinfo=UTC),
    )

    assert await mirror.mirror(project.id, edited)
    archived = await _row(world, project.id)
    assert await mirror.mirror(project.id, replace(edited, archived=False, supervisor=None))
    restored = await _row(world, project.id)

    assert (archived.pinned, archived.supervisor_name) == (True, "Сидоров И. И.")
    assert archived.archived_at is not None
    assert archived.updated_at == datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
    assert (restored.archived_at, restored.supervisor_name) == (None, None)


async def test__mirror__unknown_project__false(world: World) -> None:
    project = world.make()

    assert not await ProjectCatalogMirror(world.sessions).mirror(project.id, project)


async def test__mirroring_repository__save__copies_after_drain(world: World) -> None:
    project = await world.add("Before")
    repo = MirroringProjectRepository(world.repo, world.volume, ProjectCatalogMirror(world.sessions))

    repo.save(replace(project, name="Renamed"))
    await repo.drain()

    assert (await _row(world, project.id)).name == "Renamed"
    loaded = repo.get(project.folder)
    assert loaded is not None
    assert loaded.name == "Renamed"


async def test__mirroring_repository__save_inside_transaction__copy_runs_in_own_session(world: World) -> None:
    project = await world.add("Before")
    seen: list[object] = []

    class _Spy(ProjectCatalogMirror):
        async def mirror(self, project_id: UUID, project: Project) -> bool:
            seen.append(live_ambient())
            return await super().mirror(project_id, project)

    repo = MirroringProjectRepository(world.repo, world.volume, _Spy(world.sessions))

    async with world.sessions.begin():
        repo.save(replace(project, name="Renamed"))
        await asyncio.sleep(0)  # задача копии стартует при ещё открытой транзакции запроса
    await repo.drain()

    assert seen == [None]  # копия не делит сессию запроса с основным кодом
    assert (await _row(world, project.id)).name == "Renamed"


async def test__mirroring_repository__folder_outside_volume__only_inner_save(world: World, tmp_path: Path) -> None:
    repo = MirroringProjectRepository(world.repo, world.volume, ProjectCatalogMirror(world.sessions))
    folder = tmp_path / "elsewhere"
    folder.mkdir()

    repo.save(replace(make_project(folder=folder), id=uuid4()))
    await repo.drain()

    assert world.repo.get(folder) is not None


async def test__reconcile__missing_folder__marked_and_restored(world: World) -> None:
    present = await world.add("Present")
    gone = await world.add("Gone")
    world.volume.remove(gone.id)
    reconciler = ProjectCatalogReconciler(world.sessions, world.volume, world.repo)

    report = await reconciler.reconcile()

    assert report.checked == 2
    assert report.missing == [gone.id]
    assert (await _row(world, gone.id)).volume_missing_at is not None
    assert (await _row(world, present.id)).volume_missing_at is None

    world.volume.allocate(gone.id)
    world.repo.save(replace(gone, name="Gone"))
    report = await reconciler.reconcile()

    assert report.restored == [gone.id]
    assert (await _row(world, gone.id)).volume_missing_at is None


async def test__reconcile__stale_copy__refreshed_from_project_json(world: World) -> None:
    project = await world.add("Before")
    world.repo.save(replace(project, name="Edited by hand"))

    report = await ProjectCatalogReconciler(world.sessions, world.volume, world.repo).reconcile()

    assert report.refreshed == [project.id]
    assert (await _row(world, project.id)).name == "Edited by hand"


async def test__reconcile__broken_project_json__does_not_stop_others(world: World) -> None:
    broken = await world.add("Broken")
    fine = await world.add("Fine")
    (broken.folder / "project.json").write_text("{not json")
    world.repo.save(replace(fine, name="Fine 2"))

    report = await ProjectCatalogReconciler(world.sessions, world.volume, world.repo).reconcile()

    assert report.checked == 2
    assert report.refreshed == [fine.id]


async def test__reconcile__deleted_rows__skipped(world: World) -> None:
    project = await world.add()
    await world.locator.unregister(project.folder)
    world.volume.remove(project.id)

    report = await ProjectCatalogReconciler(world.sessions, world.volume, world.repo).reconcile()

    assert report.checked == 0
