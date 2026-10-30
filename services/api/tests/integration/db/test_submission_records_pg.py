"""PostgresPackSubmissionRepository: запись сдачи без папки пакета, снимок автора, изоляция проектов."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.submission import SubmissionRow
from hse_doc_studio.infra.db.repositories.identity import SqlUserRepository
from hse_doc_studio.infra.db.repositories.projects import PostgresProjectLocator
from hse_doc_studio.infra.db.repositories.submission import PostgresPackSubmissionRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.persistence.project import JsonProjectRepository
from hse_doc_studio.infra.projects.volume import LocalDiskProjectVolume
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.contract.test_identity_contract import make_user
from tests.contract.test_submission_contract import make_submission
from tests.factories import make_document, make_project
from tests.fixtures.actors import as_actor

pytestmark = pytest.mark.pg

_ANNA = Actor.user("anna", name="Анна")


@dataclass
class World:
    sessions: SessionProvider
    volume: LocalDiskProjectVolume
    projects: JsonProjectRepository
    locator: PostgresProjectLocator
    repo: PostgresPackSubmissionRepository

    async def add_project(self) -> tuple[Path, object]:
        project_id = uuid4()
        folder = self.volume.allocate(project_id)
        self.projects.save(replace(make_project(folder=folder, documents=[make_document()]), id=project_id))
        with as_actor(_ANNA):
            await self.locator.register(folder)
        return folder, project_id

    async def rows(self) -> list[SubmissionRow]:
        async with self.sessions.use() as session:
            rows = list((await session.execute(select(SubmissionRow))).scalars())
            session.expunge_all()
            return rows


@pytest_asyncio.fixture
async def world(pg_migrated_engine: AsyncEngine, tmp_path: Path) -> World:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    await SqlUserRepository(sessions).add(make_user("anna"))
    volume = LocalDiskProjectVolume(tmp_path / "projects")
    projects = JsonProjectRepository()
    return World(
        sessions,
        volume,
        projects,
        PostgresProjectLocator(sessions, volume, projects),
        PostgresPackSubmissionRepository(sessions, volume),
    )


async def test__save__then_get__round_trips_with_relative_archive_and_composition(world: World) -> None:
    folder, _ = await world.add_project()
    record = make_submission(folder, output_dir=None, artifact_key="artifacts/x/submissions/y/final.zip")

    await world.repo.save(record)

    assert await world.repo.get(folder, record.id) == record
    [row] = await world.rows()
    assert row.output_path == str(Path("submissions") / record.output_path.name)
    assert row.artifact_key == "artifacts/x/submissions/y/final.zip"
    assert row.data["doc_items"] == [{"doc_id": "vkr", "signatures": ["student"]}]


async def test__save__output_dir_is_not_stored(world: World) -> None:
    folder, _ = await world.add_project()
    record = make_submission(folder)

    await world.repo.save(record)

    loaded = await world.repo.get(folder, record.id)
    assert loaded is not None
    assert loaded.output_dir is None


async def test__save__same_id__updates_in_place(world: World) -> None:
    folder, _ = await world.add_project()
    record = make_submission(folder)
    await world.repo.save(record)

    await world.repo.save(replace(record, artifact_key="k/final.zip"))

    loaded = await world.repo.get(folder, record.id)
    assert loaded is not None
    assert loaded.artifact_key == "k/final.zip"
    assert len(await world.rows()) == 1


async def test__save__under_user__keeps_author_snapshot_and_later_system_save_does_not_erase_it(world: World) -> None:
    folder, _ = await world.add_project()
    record = make_submission(folder)
    with as_actor(_ANNA):
        await world.repo.save(record)

    await world.repo.save(replace(record, artifact_key="k/final.zip"))

    [row] = await world.rows()
    assert (row.actor_id, row.actor_name) == ("anna", "Анна")


async def test__list_for_project__oldest_first_and_isolated(world: World) -> None:
    mine, _ = await world.add_project()
    theirs, _ = await world.add_project()
    late, early = make_submission(mine, minutes=9), make_submission(mine, minutes=1)
    other = make_submission(theirs)
    for record in (late, early, other):
        await world.repo.save(record)

    assert [r.id for r in await world.repo.list_for_project(mine)] == [early.id, late.id]
    assert await world.repo.get(mine, other.id) is None


async def test__project_removed__its_records_are_removed(world: World) -> None:
    folder, project_id = await world.add_project()
    await world.repo.save(make_submission(folder))

    async with world.sessions.use() as session:
        await session.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})

    assert await world.rows() == []
