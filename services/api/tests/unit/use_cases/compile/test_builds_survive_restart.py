"""Выкатка api посреди облачной сборки: задача на раннере жива, и запись сборки получает её итог.

Так было 08.11.2026: сборку topic_application подхватила очередь, но восстановление при старте тут же закрыло её
запись как неудачную («[stale] server restarted…»), и итог раннера отбрасывался, раз запись уже готова.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.compile.failure import INTERRUPTED
from hse_doc_studio.core.entities import CompileRecord
from hse_doc_studio.core.enums import CompileStatus, DocumentStatus, EngineType
from hse_doc_studio.core.jobs.codec import encode_result
from hse_doc_studio.core.jobs.entities import CompileResult, JobResult, JobSpec
from hse_doc_studio.core.jobs.enums import JobStatus
from hse_doc_studio.core.jobs.queue import RunnerRef
from hse_doc_studio.infra.jobs.queue_dispatcher import QueueJobDispatcher
from hse_doc_studio.infra.persistence.project import JsonProjectRepository
from hse_doc_studio.infra.projects.volume import LocalDiskProjectVolume
from hse_doc_studio.use_cases.compile.compile_hooks_factory import CompileJobHooksFactory
from hse_doc_studio.use_cases.compile.recover_stale_compiles import RecoverStaleCompilesUC

from tests.factories import make_document, make_project
from tests.fakes.compile import InMemoryCompileRepository
from tests.fakes.job_apply import InMemoryApplyLedger
from tests.fakes.job_queue import InMemoryJobQueue
from tests.fakes.project_locator import InMemoryProjectLocator
from tests.fakes.runners import InMemoryRunnerRepository
from tests.unit.core.jobs.samples import make_compile_spec
from tests.unit.infra.jobs.test_queue_dispatcher import FakeUploader, _until

_PROJECT = uuid4()


class World:
    """База (очередь, записи сборок, проекты) переживает рестарт; память процесса api нет."""

    def __init__(self, tmp_path: Path) -> None:
        self.volume = LocalDiskProjectVolume(tmp_path / "volume")
        self.folder = self.volume.allocate(_PROJECT)
        (self.folder / "tz").mkdir()
        (self.folder / "tz" / "main.tex").write_text("x", encoding="utf-8", newline="\n")
        self.queue = InMemoryJobQueue()
        self.ledger = InMemoryApplyLedger(self.queue)
        self.compiles = InMemoryCompileRepository()
        self.projects = JsonProjectRepository()
        project = make_project(folder=self.folder, documents=[make_document("tz", status=DocumentStatus.building)])
        self.projects.save(project)
        self.locator = InMemoryProjectLocator()
        self.locator.add(project)
        self.vcs = MagicMock()
        self.vcs.is_available.return_value = False
        self.locks = MagicMock()
        self.locks.for_folder.side_effect = lambda _folder: self._lock()
        self.artifacts = AsyncMock()
        self.artifacts.fingerprint_pdf.return_value = None

    @asynccontextmanager
    async def _lock(self) -> Any:
        yield

    def factory(self) -> CompileJobHooksFactory:
        return CompileJobHooksFactory(
            compile_repo=self.compiles,
            project_repo=self.projects,
            changelog_repo=MagicMock(),
            template_repo=MagicMock(),
            vcs_service=self.vcs,
            vcs_locks=self.locks,
            artifacts=self.artifacts,
        )

    def dispatcher(self, *, factory: CompileJobHooksFactory | None = None) -> QueueJobDispatcher:
        return QueueJobDispatcher(
            self.queue,
            FakeUploader(),
            InMemoryRunnerRepository(),
            ledger=self.ledger,
            hooks_factory=factory,
            volume=self.volume,
            poll_interval_s=0.005,
        )

    def spec(self) -> JobSpec:
        return replace(
            make_compile_spec(),
            id=uuid4(),
            project_id=_PROJECT,
            actor=Actor.user(str(uuid4()), "Иван", source=ActorSource.session),
            local_root=self.folder,
        )

    async def pending_record(self, spec: JobSpec) -> None:
        """Как `TriggerCompileUC`: запись `pending` до постановки задачи."""
        await self.compiles.save(
            CompileRecord(
                id=spec.id,
                project_folder=self.folder,
                doc_id="tz",
                engine=EngineType.xelatex,
                status=CompileStatus.pending,
                started_at=datetime.now(UTC),
                finished_at=None,
                log="",
                output_path=None,
                check_results=[],
                pages=None,
            )
        )

    async def record(self, spec: JobSpec) -> CompileRecord:
        found = await self.compiles.get_for_project(self.folder, spec.id)
        assert found is not None
        return found

    def doc_status(self) -> DocumentStatus:
        project = self.projects.get(self.folder)
        assert project is not None
        return project.documents[0].status

    async def restart(self) -> tuple[QueueJobDispatcher, RecoverStaleCompilesUC]:
        """Старт нового процесса в порядке entrypoint: сначала очередь, потом записи сборок."""
        dispatcher = self.dispatcher(factory=self.factory())
        await dispatcher.recover()
        return dispatcher, RecoverStaleCompilesUC(self.projects, self.locator, self.compiles, dispatcher)


async def _kill(dispatcher: QueueJobDispatcher) -> None:
    for task in list(dispatcher._tasks):
        task.cancel()
    await asyncio.sleep(0)


async def test__restart_while_runner_builds__record_waits_and_gets_the_runner_result(tmp_path: Path) -> None:
    world = World(tmp_path)
    spec = world.spec()
    await world.pending_record(spec)
    old = world.dispatcher()
    old.submit(spec, world.factory().for_spec(spec))  # type: ignore[arg-type]
    await _until(lambda: world.queue._jobs.get(spec.id) is not None)
    job = await world.queue.claim(RunnerRef(id=uuid4(), tags=frozenset({"tex"})), lease_s=45)
    assert job is not None
    await _until(lambda: world.compiles._records[(world.folder, spec.id)].status is CompileStatus.running)
    await _kill(old)

    dispatcher, stale = await world.restart()
    out = await stale.execute()

    assert (out.recovered_compiles, out.continued_compiles, out.unstuck_documents) == (0, 1, 0)
    assert (await world.record(spec)).status is CompileStatus.running
    assert world.doc_status() is DocumentStatus.building

    result = JobResult(status=JobStatus.succeeded, data=CompileResult(build_ok=True, pages=4))
    await world.queue.complete(job.id, job.attempt, JobStatus.succeeded, result=encode_result(result))
    await _until(lambda: not dispatcher.is_active(spec.id))

    record = await world.record(spec)
    assert record.status is CompileStatus.success
    assert record.pages == 4
    assert record.error_code is None
    assert "[stale]" not in record.log
    assert world.doc_status() is DocumentStatus.ok


async def test__restart_with_job_in_queue__build_is_picked_up_later_and_finishes(tmp_path: Path) -> None:
    world = World(tmp_path)
    spec = world.spec()
    await world.pending_record(spec)
    old = world.dispatcher()
    old.submit(spec, world.factory().for_spec(spec))  # type: ignore[arg-type]
    await _until(lambda: world.queue._jobs.get(spec.id) is not None)
    await _kill(old)

    dispatcher, stale = await world.restart()
    out = await stale.execute()
    assert out.continued_compiles == 1

    job = await world.queue.claim(RunnerRef(id=uuid4(), tags=frozenset({"tex"})), lease_s=45)
    assert job is not None
    result = JobResult(status=JobStatus.failed, data=CompileResult(build_ok=False))
    await world.queue.complete(job.id, job.attempt, JobStatus.failed, result=encode_result(result))
    await _until(lambda: not dispatcher.is_active(spec.id))

    record = await world.record(spec)
    # Итог самой сборки (LaTeX упал), а не «прервана»: документ тут виноват, и это видно.
    assert record.status is CompileStatus.failure
    assert record.error_code == "build_failed"


async def test__restart_before_job_reached_the_queue__record_is_interrupted_not_failed(tmp_path: Path) -> None:
    world = World(tmp_path)
    spec = world.spec()
    # Процесс умер, пока проект грузился в хранилище: запись есть, задачи в очереди нет.
    await world.pending_record(spec)

    _dispatcher, stale = await world.restart()
    out = await stale.execute()

    assert (out.recovered_compiles, out.continued_compiles, out.unstuck_documents) == (1, 0, 1)
    record = await world.record(spec)
    assert record.status is CompileStatus.cancelled
    assert record.error_code == INTERRUPTED
    assert record.finished_at is not None
    assert world.doc_status() is DocumentStatus.err
