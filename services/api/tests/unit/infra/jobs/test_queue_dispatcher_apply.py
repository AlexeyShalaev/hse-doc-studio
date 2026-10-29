"""QueueJobDispatcher: выходы на том до хуков, метка применённого и восстановление после рестарта."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.jobs.applier import ApplyError
from hse_doc_studio.core.jobs.codec import encode, encode_result
from hse_doc_studio.core.jobs.entities import CompileResult, JobResult, JobSpec
from hse_doc_studio.core.jobs.enums import JobKind, JobState, JobStatus
from hse_doc_studio.core.jobs.files import ArtifactRef
from hse_doc_studio.core.jobs.protocols import IJobHooks
from hse_doc_studio.core.jobs.queue import QueuedJob, RunnerRef
from hse_doc_studio.infra.jobs.queue_dispatcher import QueueJobDispatcher
from hse_doc_studio.infra.projects.volume import LocalDiskProjectVolume

from tests.fakes.job_apply import InMemoryApplyLedger
from tests.fakes.job_queue import InMemoryJobQueue
from tests.fakes.runners import InMemoryRunnerRepository
from tests.unit.core.jobs.samples import make_compile_spec, make_office_result, make_office_spec
from tests.unit.infra.jobs.test_queue_dispatcher import FakeUploader, _until

_USER = uuid4()
_PROJECT = uuid4()
_RUNNER = uuid4()
_PDF = ArtifactRef(path="tz/main.pdf", sha256="c" * 64, size=5)


class Journal:
    def __init__(self) -> None:
        self.events: list[str] = []


class FakeApplier:
    def __init__(self, journal: Journal) -> None:
        self.journal = journal
        self.error: ApplyError | None = None
        self.applied: list[tuple[UUID, tuple[ArtifactRef, ...]]] = []
        self.discarded: list[UUID] = []

    async def apply(self, spec: JobSpec, artifacts: Sequence[ArtifactRef]) -> None:
        self.journal.events.append("apply")
        if self.error is not None:
            raise self.error
        self.applied.append((spec.id, tuple(artifacts)))

    async def discard(self, spec: JobSpec) -> None:
        self.journal.events.append("discard")
        self.discarded.append(spec.id)


class RecordingHooks:
    def __init__(self, journal: Journal, *, fail_finish: bool = False) -> None:
        self.journal = journal
        self.fail_finish = fail_finish
        self.finished: list[tuple[JobSpec, JobResult]] = []
        self.started: list[JobSpec] = []
        self.actors: list[Actor | None] = []

    async def on_started(self, spec: JobSpec) -> bool:
        self.journal.events.append("on_started")
        self.started.append(spec)
        self.actors.append(current_actor())
        return True

    async def on_finished(self, spec: JobSpec, result: JobResult, log: str) -> None:
        self.journal.events.append("on_finished")
        self.actors.append(current_actor())
        if self.fail_finish:
            raise RuntimeError("crash before hooks completed")
        self.finished.append((spec, result))


class Factory:
    def __init__(self, hooks: RecordingHooks) -> None:
        self.hooks = hooks
        self.specs: list[JobSpec] = []

    def for_spec(self, spec: JobSpec) -> IJobHooks | None:
        self.specs.append(spec)
        return self.hooks if spec.kind is JobKind.compile else None


@dataclass
class Rig:
    queue: InMemoryJobQueue
    ledger: InMemoryApplyLedger
    journal: Journal
    applier: FakeApplier
    runners: InMemoryRunnerRepository
    uploader: FakeUploader
    volume: LocalDiskProjectVolume
    dispatcher: QueueJobDispatcher

    def restart(self, hooks: RecordingHooks) -> tuple[QueueJobDispatcher, Factory]:
        """Новый процесс api: очередь и метки в базе те же, память (хуки, отслеживание) пустая."""
        factory = Factory(hooks)
        return self._build(factory), factory

    def _build(self, factory: Factory | None) -> QueueJobDispatcher:
        return QueueJobDispatcher(
            self.queue,
            self.uploader,
            self.runners,
            applier=self.applier,
            ledger=self.ledger,
            hooks_factory=factory,
            volume=self.volume,
            poll_interval_s=0.005,
        )

    def spec(self, base: JobSpec | None = None) -> JobSpec:
        return replace(
            base or make_compile_spec(),
            id=uuid4(),
            project_id=_PROJECT,
            actor=Actor.user(str(_USER), "Иван", source=ActorSource.session),
            local_root=self.volume.path_of(_PROJECT),
        )

    async def claim(self) -> QueuedJob:
        job = await self.queue.claim(RunnerRef(id=_RUNNER, tags=frozenset({"tex", "office", "verify"})), lease_s=45)
        assert job is not None
        return job

    async def finish(self, job: QueuedJob, result: JobResult, artifacts: Sequence[ArtifactRef] = ()) -> None:
        await self.queue.complete(
            job.id, job.attempt, JobStatus.succeeded, result={**encode_result(result), "artifacts": encode(artifacts)}
        )


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    volume = LocalDiskProjectVolume(tmp_path / "volume")
    folder = volume.allocate(_PROJECT)
    (folder / "tz").mkdir()
    (folder / "tz" / "main.tex").write_text("x")
    queue = InMemoryJobQueue()
    journal = Journal()
    built = Rig(
        queue,
        InMemoryApplyLedger(queue),
        journal,
        FakeApplier(journal),
        InMemoryRunnerRepository(),
        FakeUploader(),
        volume,
        None,  # type: ignore[arg-type]
    )
    built.dispatcher = built._build(None)
    return built


def _ok() -> JobResult:
    return JobResult(status=JobStatus.succeeded, data=CompileResult(build_ok=True, pages=3))


async def test__submit__artifacts__applied_before_hooks_then_marked_and_discarded(rig: Rig) -> None:
    hooks = RecordingHooks(rig.journal)
    spec = rig.spec()

    rig.dispatcher.submit(spec, hooks)
    await _until(lambda: rig.queue._jobs.get(spec.id) is not None)
    job = await rig.claim()
    await rig.finish(job, _ok(), [_PDF])
    await _until(lambda: spec.id in rig.ledger.applied and "discard" in rig.journal.events)

    assert rig.journal.events == ["on_started", "apply", "on_finished", "discard"]
    assert rig.applier.applied == [(spec.id, (_PDF,))]
    assert hooks.finished[0][1].status is JobStatus.succeeded


async def test__submit__apply_rejected__failed_result_with_typed_code_and_job_still_marked(rig: Rig) -> None:
    rig.applier.error = ApplyError("output_unsafe_path", "tz/.build is a link")
    hooks = RecordingHooks(rig.journal)
    spec = rig.spec()

    rig.dispatcher.submit(spec, hooks)
    await _until(lambda: rig.queue._jobs.get(spec.id) is not None)
    await rig.finish(await rig.claim(), _ok(), [_PDF])
    await _until(lambda: spec.id in rig.ledger.applied)

    result = hooks.finished[0][1]
    assert result.status is JobStatus.failed
    assert result.error is not None
    assert result.error.code == "output_unsafe_path"
    assert isinstance(result.data, CompileResult)
    assert result.data.build_ok is False


async def test__run__office_outputs_applied_before_result_is_returned(rig: Rig) -> None:
    spec = rig.spec(make_office_spec())
    task = asyncio.create_task(rig.dispatcher.run(spec))
    await _until(lambda: rig.queue._jobs.get(spec.id) is not None)

    await rig.finish(await rig.claim(), make_office_result(), [_PDF])
    result = await task

    assert result.status is JobStatus.succeeded
    assert rig.journal.events == ["apply", "discard"]
    assert spec.id in rig.ledger.applied


async def test__recover__crash_between_apply_and_hooks__next_start_applies_again_and_runs_hooks(rig: Rig) -> None:
    broken = RecordingHooks(rig.journal, fail_finish=True)
    spec = rig.spec()
    rig.dispatcher.submit(spec, broken)
    await _until(lambda: rig.queue._jobs.get(spec.id) is not None)
    await rig.finish(await rig.claim(), _ok(), [_PDF])
    await _until(lambda: "on_finished" in rig.journal.events)
    await _until(lambda: not rig.dispatcher.is_active(spec.id))
    assert rig.ledger.applied == set()
    rig.journal.events.clear()

    hooks = RecordingHooks(rig.journal)
    dispatcher, factory = rig.restart(hooks)
    report = await dispatcher.recover()

    assert (report.finished, report.adopted, report.failed) == (1, 0, 0)
    assert rig.journal.events == ["apply", "on_finished", "discard"]
    assert spec.id in rig.ledger.applied
    (rebuilt, result) = hooks.finished[0]
    assert result.status is JobStatus.succeeded
    assert rebuilt.local_root == rig.volume.path_of(_PROJECT)
    assert rebuilt.actor.id == str(_USER)
    assert rebuilt.actor.source is ActorSource.job
    assert hooks.actors == [rebuilt.actor]
    assert current_actor() is None


async def test__recover__second_start_after_success__does_nothing(rig: Rig) -> None:
    spec = rig.spec()
    rig.dispatcher.submit(spec, RecordingHooks(rig.journal))
    await _until(lambda: rig.queue._jobs.get(spec.id) is not None)
    await rig.finish(await rig.claim(), _ok(), [_PDF])
    await _until(lambda: spec.id in rig.ledger.applied)
    rig.journal.events.clear()

    dispatcher, _ = rig.restart(RecordingHooks(rig.journal))
    report = await dispatcher.recover()

    assert (report.finished, report.adopted) == (0, 0)
    assert rig.journal.events == []


async def test__recover__running_job_after_restart__hooks_rebuilt_and_finished_once(rig: Rig) -> None:
    spec = rig.spec()
    rig.dispatcher.submit(spec, RecordingHooks(rig.journal))
    await _until(lambda: rig.queue._jobs.get(spec.id) is not None)
    job = await rig.claim()
    await _until(lambda: "on_started" in rig.journal.events)
    for task in list(rig.dispatcher._tasks):
        task.cancel()
    await asyncio.sleep(0)
    rig.journal.events.clear()

    hooks = RecordingHooks(rig.journal)
    dispatcher, factory = rig.restart(hooks)
    report = await dispatcher.recover()
    assert (report.finished, report.adopted) == (0, 1)
    assert dispatcher.is_active(spec.id)
    await _until(lambda: hooks.started != [])

    await rig.finish(job, _ok(), [_PDF])
    await _until(lambda: spec.id in rig.ledger.applied)
    await _until(lambda: not dispatcher.is_active(spec.id))

    assert rig.journal.events == ["on_started", "apply", "on_finished", "discard"]
    assert [s.id for s in factory.specs] == [spec.id]
    assert hooks.actors[0] is not None
    assert hooks.actors[0].source is ActorSource.job


async def test__recover__queued_job_replaced_by_newer__old_hooks_see_superseded(rig: Rig) -> None:
    old, new = rig.spec(), rig.spec()
    rig.dispatcher.submit(old, RecordingHooks(rig.journal))
    await _until(lambda: rig.queue._jobs.get(old.id) is not None)
    rig.dispatcher.submit(new, RecordingHooks(rig.journal))
    await _until(lambda: rig.queue._jobs.get(new.id) is not None)
    await _until(lambda: old.id in rig.ledger.applied)
    rig.journal.events.clear()
    assert (await rig.queue.get(old.id)).state is JobState.cancelled  # type: ignore[union-attr]

    # Процесс упал до метки: имитируем снятием метки и новым стартом.
    rig.ledger.applied.discard(old.id)
    hooks = RecordingHooks(rig.journal)
    dispatcher, _ = rig.restart(hooks)
    report = await dispatcher.recover()

    assert report.finished == 1
    (spec, result) = hooks.finished[0]
    assert spec.id == old.id
    assert result.status is JobStatus.cancelled
    assert result.error is not None
    assert result.error.code == "superseded"


async def test__recover__without_ledger__is_a_noop(rig: Rig) -> None:
    dispatcher = QueueJobDispatcher(rig.queue, rig.uploader, rig.runners)

    report = await dispatcher.recover()

    assert (report.finished, report.adopted, report.failed) == (0, 0, 0)
