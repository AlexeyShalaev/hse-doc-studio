"""Жизненный цикл проекта на сервере: создание на томе и в БД одной транзакцией, мягкое удаление, стирание по сроку."""

from __future__ import annotations

import shutil
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from hse_doc_studio.api.config import settings
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.enums import EngineType, Lang, ProjectKind, ProjectStaffing
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow, ProjectRow
from hse_doc_studio.infra.db.repositories.identity import SqlUserRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.di.containers.api import create_container
from hse_doc_studio.infra.projects.purge import ProjectPurger
from hse_doc_studio.infra.projects.volume import LocalDiskProjectVolume
from hse_doc_studio.use_cases.projects import create_project as create_project_module
from hse_doc_studio.use_cases.projects.create_project import CreateProjectInput, CreateProjectUC
from hse_doc_studio.use_cases.projects.unregister_project import UnregisterProjectInput, UnregisterProjectUC
from sqlalchemy import func, select, update

from tests.contract.test_identity_contract import make_user
from tests.fixtures.actors import as_actor

if TYPE_CHECKING:
    from dishka import AsyncContainer
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg

OWNER = Actor.user("user-a")


@dataclass
class World:
    container: AsyncContainer
    sessions: SessionProvider
    root: Path

    def folders(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir()) if self.root.exists() else []

    async def rows(self) -> list[ProjectRow]:
        async with self.sessions.use() as session:
            return list((await session.execute(select(ProjectRow))).scalars().all())

    async def member_count(self) -> int:
        async with self.sessions.use() as session:
            return (await session.execute(select(func.count()).select_from(ProjectMemberRow))).scalar_one()


def _input(folder: Path | None = None, name: str = "Курсовая") -> CreateProjectInput:
    return CreateProjectInput(
        folder=folder,
        pack_id="hse-cs-se",
        template_id="vkr",
        version="2026.1",
        name=name,
        kind=ProjectKind.research,
        staffing=ProjectStaffing.solo,
        lang=Lang.ru,
        engine=EngineType.xelatex,
        authors=[],
        supervisor=None,
        co_supervisor=None,
        meta={},
    )


@pytest_asyncio.fixture
async def world(
    pg_migrated_engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[World]:
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings.server, "projects_root", tmp_path / "projects")
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    await SqlUserRepository(sessions).add(make_user("user-a"))
    container = create_container(StudioMode.server, engine=pg_migrated_engine)
    try:
        yield World(container, sessions, tmp_path / "projects")
    finally:
        await container.close()


async def _create(world: World, inp: CreateProjectInput | None = None) -> UUID:
    async with world.container() as request:
        uc = await request.get(CreateProjectUC)
        with as_actor(OWNER):
            return (await uc.execute(inp or _input())).project.id


async def _delete(world: World, project_id: UUID) -> None:
    async with world.container() as request:
        uc = await request.get(UnregisterProjectUC)
        with as_actor(OWNER):
            await uc.execute(UnregisterProjectInput(project_id=project_id))


async def test__create__allocates_folder_and_writes_rows(world: World) -> None:
    project_id = await _create(world)

    assert world.folders() == [str(project_id)]
    assert (world.root / str(project_id) / ".hse-studio" / "project.json").is_file()
    [row] = await world.rows()
    assert (row.id, row.owner_user_id, row.workspace_path, row.deleted_at) == (
        project_id,
        "user-a",
        str(project_id),
        None,
    )
    assert await world.member_count() == 1


async def test__create__failure_after_folder_allocated__rolls_back_both_sides(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(**_: object) -> None:
        raise RuntimeError("render failed")

    monkeypatch.setattr(create_project_module, "_render_template_files", boom)

    with pytest.raises(RuntimeError, match="render failed"):
        await _create(world)

    assert world.folders() == []
    assert await world.rows() == []
    assert await world.member_count() == 0


async def test__create__folder_field__refused_and_nothing_allocated(world: World, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="folder"):
        await _create(world, _input(tmp_path / "mine"))

    assert world.folders() == []
    assert await world.rows() == []


async def test__create__unknown_template__nothing_allocated(world: World) -> None:
    inp = _input()
    inp.version = "no-such-version"

    with pytest.raises(Exception, match="не найдена|not found"):
        await _create(world, inp)

    assert world.folders() == []


async def test__delete__soft_deletes_and_keeps_folder(world: World) -> None:
    project_id = await _create(world)

    await _delete(world, project_id)

    [row] = await world.rows()
    assert row.deleted_at is not None
    assert world.folders() == [str(project_id)]


async def test__delete__unknown_project__not_found(world: World) -> None:
    with pytest.raises(NotFoundError):
        await _delete(world, uuid4())


def _purger(world: World, days: int = 30) -> ProjectPurger:
    return ProjectPurger(world.sessions, LocalDiskProjectVolume(world.root), timedelta(days=days))


async def _age(world: World, project_id: UUID, days: int) -> None:
    stmt = (
        update(ProjectRow)
        .where(ProjectRow.id == project_id)
        .values(deleted_at=datetime.now(tz=timezone.utc) - timedelta(days=days))
    )
    async with world.sessions.use() as session:
        await session.execute(stmt)


async def test__purge__expired_project__folder_and_rows_gone(world: World) -> None:
    project_id = await _create(world)
    await _delete(world, project_id)
    await _age(world, project_id, 31)

    report = await _purger(world).purge_expired()

    assert report.purged == [project_id]
    assert world.folders() == []
    assert await world.rows() == []
    assert await world.member_count() == 0


async def test__purge__freshly_deleted_and_live_projects__untouched(world: World) -> None:
    fresh = await _create(world)
    await _delete(world, fresh)
    await _age(world, fresh, 2)
    live = await _create(world, _input(name="Живой"))

    report = await _purger(world).purge_expired()

    assert report.purged == []
    assert world.folders() == sorted([str(fresh), str(live)])
    assert len(await world.rows()) == 2


async def test__purge__zero_retention__never_purges(world: World) -> None:
    project_id = await _create(world)
    await _delete(world, project_id)
    await _age(world, project_id, 4000)

    assert (await _purger(world, days=0).purge_expired()).purged == []
    assert world.folders() == [str(project_id)]


async def test__purge__symlinked_folder__link_removed_target_kept(world: World, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "precious.txt").write_text("keep")
    project_id = await _create(world)
    await _delete(world, project_id)
    await _age(world, project_id, 31)
    folder = world.root / str(project_id)
    shutil.rmtree(folder)
    folder.symlink_to(outside, target_is_directory=True)

    await _purger(world).purge_expired()

    assert (outside / "precious.txt").read_text() == "keep"
    assert not folder.exists()
    assert await world.rows() == []


async def test__purge__tampered_workspace_path__does_not_leave_root(world: World, tmp_path: Path) -> None:
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "data.txt").write_text("keep")
    project_id = await _create(world)
    await _delete(world, project_id)
    await _age(world, project_id, 31)
    async with world.sessions.use() as session:
        await session.execute(update(ProjectRow).where(ProjectRow.id == project_id).values(workspace_path=str(victim)))

    await _purger(world).purge_expired()

    assert (victim / "data.txt").read_text() == "keep"
    assert world.folders() == []


async def test__purge__folder_already_missing__row_still_removed(world: World) -> None:
    project_id = await _create(world)
    await _delete(world, project_id)
    await _age(world, project_id, 31)
    shutil.rmtree(world.root / str(project_id))

    report = await _purger(world).purge_expired()

    assert report.purged == [project_id]
    assert await world.rows() == []
