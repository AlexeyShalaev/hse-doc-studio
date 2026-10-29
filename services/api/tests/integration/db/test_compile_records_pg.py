"""PostgresCompileRepository: история сборок, предел записей и лога, снимок автора, восстановление."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.enums import CheckSeverity, CompileStatus, DocumentStatus
from hse_doc_studio.core.projects.volume import UnsafePathError
from hse_doc_studio.core.value_objects import CheckLocation, CheckResult
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.compile import CompileRecordRow
from hse_doc_studio.infra.db.repositories.compile import PostgresCompileRepository
from hse_doc_studio.infra.db.repositories.identity import SqlUserRepository
from hse_doc_studio.infra.db.repositories.projects import PostgresProjectLocator
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.persistence.project import JsonProjectRepository
from hse_doc_studio.infra.projects.volume import LocalDiskProjectVolume
from hse_doc_studio.use_cases.compile.recover_stale_compiles import RecoverStaleCompilesUC
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.contract.test_compile_contract import make_record
from tests.contract.test_identity_contract import make_user
from tests.factories import make_document, make_project
from tests.fixtures.actors import as_actor

pytestmark = pytest.mark.pg

_ANNA = Actor.user("anna", name="Анна")
_KEEP = 3
_LOG_LIMIT = 2048


@dataclass
class World:
    sessions: SessionProvider
    volume: LocalDiskProjectVolume
    projects: JsonProjectRepository
    locator: PostgresProjectLocator
    repo: PostgresCompileRepository

    async def add_project(self, *, building: bool = False) -> Path:
        project_id = uuid4()
        folder = self.volume.allocate(project_id)
        document = replace(make_document(), status=DocumentStatus.building if building else DocumentStatus.ok)
        self.projects.save(replace(make_project(folder=folder, documents=[document]), id=project_id))
        with as_actor(_ANNA):
            await self.locator.register(folder)
        return folder

    async def rows(self) -> list[CompileRecordRow]:
        async with self.sessions.use() as session:
            rows = list((await session.execute(select(CompileRecordRow))).scalars())
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
        PostgresCompileRepository(sessions, volume, keep_per_document=_KEEP, log_limit_bytes=_LOG_LIMIT),
    )


async def test__save__then_get__round_trips_with_check_results_and_relative_output(world: World) -> None:
    folder = await world.add_project()
    check = CheckResult(
        rule_id="gost/margins", severity=CheckSeverity.warn, message="поля", location=CheckLocation("vkr/vkr.tex", 3)
    )
    record = make_record(folder, check_results=[check], output_path=folder / "vkr" / "vkr.pdf")

    await world.repo.save(record)

    assert await world.repo.get_for_project(folder, record.id) == record
    [row] = await world.rows()
    assert row.output_path == str(Path("vkr") / "vkr.pdf")


async def test__save__same_id__updates_in_place(world: World) -> None:
    folder = await world.add_project()
    record = make_record(folder, status=CompileStatus.running, finished_at=None, log="")
    await world.repo.save(record)

    await world.repo.save(replace(record, status=CompileStatus.failure, log="boom"))

    loaded = await world.repo.get_for_project(folder, record.id)
    assert loaded is not None
    assert (loaded.status, loaded.log) == (CompileStatus.failure, "boom")
    assert len(await world.rows()) == 1


async def test__list_for_document__oldest_first(world: World) -> None:
    folder = await world.add_project()
    late, early, middle = (make_record(folder, minutes=m) for m in (20, 1, 10))
    other_doc = make_record(folder, doc_id="tz", minutes=5)
    for record in (late, early, middle, other_doc):
        await world.repo.save(record)

    assert [r.id for r in await world.repo.list_for_document(folder, "vkr")] == [early.id, middle.id, late.id]


async def test__save__over_limit__keeps_newest_records_of_that_document_only(world: World) -> None:
    folder = await world.add_project()
    other = make_record(folder, doc_id="tz")
    await world.repo.save(other)
    records = [make_record(folder, minutes=m) for m in range(_KEEP + 2)]
    for record in records:
        await world.repo.save(record)

    kept = await world.repo.list_for_document(folder, "vkr")

    assert [r.id for r in kept] == [r.id for r in records[-_KEEP:]]
    assert await world.repo.get_for_project(folder, other.id) is not None


async def test__save__over_limit__unfinished_record_is_never_trimmed(world: World) -> None:
    folder = await world.add_project()
    stuck = make_record(folder, status=CompileStatus.running, finished_at=None, minutes=0)
    await world.repo.save(stuck)
    for minutes in range(1, _KEEP + 3):
        await world.repo.save(make_record(folder, minutes=minutes))

    assert await world.repo.get_for_project(folder, stuck.id) is not None


async def test__save__long_log__keeps_tail_within_limit(world: World) -> None:
    folder = await world.add_project()
    log = "начало\n" + "строка лога\n" * 1000 + "Итог: ошибка в main.tex"
    record = make_record(folder, log=log)

    await world.repo.save(record)

    loaded = await world.repo.get_for_project(folder, record.id)
    assert loaded is not None
    assert len(loaded.log.encode("utf-8")) <= _LOG_LIMIT
    assert loaded.log.startswith("[... начало лога обрезано")
    assert loaded.log.endswith("Итог: ошибка в main.tex")


async def test__save__log_within_limit__stored_as_is(world: World) -> None:
    folder = await world.add_project()
    record = make_record(folder, log="короткий лог")

    await world.repo.save(record)

    loaded = await world.repo.get_for_project(folder, record.id)
    assert loaded is not None
    assert loaded.log == "короткий лог"


async def test__save__actor_snapshot_taken_on_create_and_kept_by_background_update(world: World) -> None:
    folder = await world.add_project()
    record = make_record(folder, status=CompileStatus.pending, finished_at=None)
    with as_actor(_ANNA):
        await world.repo.save(record)

    with as_actor(None):
        await world.repo.save(replace(record, status=CompileStatus.success))

    [row] = await world.rows()
    assert (row.actor_id, row.actor_name, row.status) == ("anna", "Анна", "success")


async def test__save__without_actor__record_has_no_author(world: World) -> None:
    folder = await world.add_project()

    with as_actor(None):
        await world.repo.save(make_record(folder))

    [row] = await world.rows()
    assert row.actor_id is None


async def test__records__are_isolated_between_projects(world: World) -> None:
    mine, theirs = await world.add_project(), await world.add_project()
    record = make_record(mine)
    await world.repo.save(record)

    assert await world.repo.get_for_project(theirs, record.id) is None
    assert await world.repo.list_for_document(theirs, "vkr") == []
    assert await world.repo.list_unfinished(theirs) == []


async def test__records__folder_outside_volume__rejected(world: World, tmp_path: Path) -> None:
    with pytest.raises(UnsafePathError):
        await world.repo.list_for_document(tmp_path / str(uuid4()), "vkr")


async def test__project_removed_from_catalog__records_cascade(world: World) -> None:
    folder = await world.add_project()
    await world.repo.save(make_record(folder))
    project_id: UUID = world.volume.id_of(folder)

    async with world.sessions.use() as session:
        from hse_doc_studio.infra.db.orm.projects import ProjectRow

        await session.delete(await session.get(ProjectRow, project_id))

    assert await world.rows() == []


async def test__recover_stale_compiles__fails_stuck_records_and_unsticks_documents(world: World) -> None:
    folder = await world.add_project(building=True)
    stuck = make_record(folder, status=CompileStatus.running, finished_at=None, log="шаг 1")
    done = make_record(folder, minutes=5)
    await world.repo.save(stuck)
    await world.repo.save(done)

    with as_actor(None):
        result = await RecoverStaleCompilesUC(world.projects, world.locator, world.repo).execute()

    assert (result.recovered_compiles, result.unstuck_documents) == (1, 1)
    recovered = await world.repo.get_for_project(folder, stuck.id)
    assert recovered is not None
    assert recovered.status is CompileStatus.failure
    assert recovered.log.startswith("шаг 1\n[stale]")
    assert await world.repo.list_unfinished(folder) == []
