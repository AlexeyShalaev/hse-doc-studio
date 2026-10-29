"""QueueJobDispatcher: preflight, постановка со staging, хуки по одному разу, run и фоновые задачи."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.jobs.codec import decode_envelope, encode_result
from hse_doc_studio.core.jobs.entities import CompileResult, JobResult, JobSpec
from hse_doc_studio.core.jobs.enums import JobErrorCategory, JobKind, JobState, JobStatus
from hse_doc_studio.core.jobs.errors import NoRunnerAvailableError
from hse_doc_studio.core.jobs.files import ManifestFile
from hse_doc_studio.core.jobs.queue import QueuedJob, RunnerRef
from hse_doc_studio.core.jobs.runners import Runner
from hse_doc_studio.core.storage.manifest import ManifestFileTooLargeError, ManifestLimits
from hse_doc_studio.infra.jobs.queue_dispatcher import QueueJobDispatcher

from tests.fakes.job_queue import InMemoryJobQueue
from tests.fakes.runners import InMemoryRunnerRepository
from tests.unit.core.jobs.samples import make_compile_spec, make_office_result, make_office_spec, make_verify_spec

_USER = uuid4()
_RUNNER_ID = uuid4()
_NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


class FakeUploader:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, Path, tuple[str, ...]]] = []
        self.error: Exception | None = None

    async def ensure(
        self, project_id: UUID, folder: Path, paths: Sequence[str], limits: ManifestLimits | None = None
    ) -> list[ManifestFile]:
        self.calls.append((project_id, folder, tuple(paths)))
        if self.error is not None:
            raise self.error
        return [ManifestFile(path=p, sha256="a" * 64, size=3) for p in paths]


class Hooks:
    def __init__(self, *, started: bool = True) -> None:
        self.events: list[str] = []
        self.started = started
        self.finished: list[tuple[JobResult, str]] = []

    async def on_started(self, spec: JobSpec) -> bool:
        self.events.append("on_started")
        return self.started

    async def on_finished(self, spec: JobSpec, result: JobResult, log: str) -> None:
        self.events.append("on_finished")
        self.finished.append((result, log))


@dataclass
class Rig:
    dispatcher: QueueJobDispatcher
    queue: InMemoryJobQueue
    runners: InMemoryRunnerRepository
    uploader: FakeUploader
    folder: Path

    def spec(self, base: JobSpec | None = None, *, job_id: UUID | None = None) -> JobSpec:
        spec = base or make_compile_spec()
        return replace(
            spec,
            id=job_id or uuid4(),
            actor=Actor.user(str(_USER), "Иван"),
            local_root=self.folder,
        )

    async def add_runner(self, *tags: str, seen: datetime | None = None, paused: bool = False) -> None:
        await self.runners.add(
            Runner(
                id=_RUNNER_ID.hex,
                name="r",
                token_hash="h",
                tags=frozenset(tags),
                concurrency=1,
                resource_class="standard",
                version="1",
                created_at=_NOW,
                last_seen_at=seen or datetime.now(UTC),
                paused=paused,
            )
        )

    async def claim(self) -> QueuedJob:
        job = await self.queue.claim(RunnerRef(id=_RUNNER_ID, tags=frozenset({"tex", "office", "verify"})), lease_s=45)
        assert job is not None
        return job

    async def finish(self, job: QueuedJob, result: JobResult, status: JobStatus = JobStatus.succeeded) -> None:
        await self.queue.complete(job.id, job.attempt, status, result={**encode_result(result), "artifacts": []})


async def _until(condition: Callable[[], bool]) -> None:
    for _ in range(1000):
        if condition():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("condition was not reached")


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    folder = tmp_path / "project"
    (folder / "tz").mkdir(parents=True)
    (folder / "tz" / "main.tex").write_text("x")
    (folder / "common").mkdir()
    (folder / "common" / "meta.tex").write_text("y")
    for junk in (".git", ".build", ".hse-studio", "submissions"):
        (folder / junk).mkdir()
        (folder / junk / "f").write_text("z")
    os.symlink("/etc/hosts", folder / "link.txt")
    queue = InMemoryJobQueue()
    runners = InMemoryRunnerRepository()
    uploader = FakeUploader()

    async def role_of(actor: Actor, project_id: UUID) -> Role | None:
        return Role.editor

    dispatcher = QueueJobDispatcher(queue, uploader, runners, role_source=role_of, poll_interval_s=0.005)
    return Rig(dispatcher, queue, runners, uploader, folder)


def _ok_compile() -> JobResult:
    return JobResult(status=JobStatus.succeeded, data=CompileResult(build_ok=True, pages=3))


async def test__preflight__without_live_runner__raises_no_runner(rig: Rig) -> None:
    with pytest.raises(NoRunnerAvailableError):
        await rig.dispatcher.preflight(rig.spec())


async def test__preflight__runner_with_tags__passes(rig: Rig) -> None:
    await rig.add_runner("tex")

    await rig.dispatcher.preflight(rig.spec())


@pytest.mark.parametrize("case", ["tags", "stale", "paused"])
async def test__preflight__unsuitable_runner__raises_no_runner(rig: Rig, case: str) -> None:
    if case == "tags":
        await rig.add_runner("office")
    elif case == "stale":
        await rig.add_runner("tex", seen=datetime.now(UTC) - timedelta(minutes=10))
    else:
        await rig.add_runner("tex", paused=True)

    with pytest.raises(NoRunnerAvailableError):
        await rig.dispatcher.preflight(rig.spec())


async def test__submit__runner_takes_job__on_started_then_on_finished_once(rig: Rig) -> None:
    hooks = Hooks()
    spec = rig.spec()

    rig.dispatcher.submit(spec, hooks)
    assert rig.dispatcher.is_active(spec.id)
    await _until(lambda: rig.queue._jobs.get(spec.id) is not None)
    assert hooks.events == []

    job = await rig.claim()
    await _until(lambda: hooks.events == ["on_started"])
    await rig.finish(job, _ok_compile())
    await _until(lambda: "on_finished" in hooks.events)
    await asyncio.sleep(0.03)

    assert hooks.events == ["on_started", "on_finished"]
    result, _log = hooks.finished[0]
    assert result.status is JobStatus.succeeded
    assert result.data == CompileResult(build_ok=True, pages=3)
    await _until(lambda: not rig.dispatcher.is_active(spec.id))


async def test__submit__stages_whole_project_without_service_dirs_and_links(rig: Rig) -> None:
    spec = rig.spec()

    rig.dispatcher.submit(spec, Hooks())
    await _until(lambda: rig.queue._jobs.get(spec.id) is not None)

    (project_id, folder, paths) = rig.uploader.calls[0]
    assert (project_id, folder) == (spec.project_id, rig.folder)
    assert sorted(paths) == ["common/meta.tex", "tz/main.tex"]


async def test__submit__queue_payload_is_an_envelope_with_manifest_and_role(rig: Rig) -> None:
    spec = rig.spec()

    rig.dispatcher.submit(spec, Hooks())
    await _until(lambda: rig.queue._jobs.get(spec.id) is not None)

    job = await rig.claim()
    envelope = decode_envelope({**job.payload, "attempt": 1, "job_token": "t"})
    assert envelope.spec.id == spec.id
    assert envelope.spec.local_root is None
    assert {m.path for m in envelope.manifest} == {"common/meta.tex", "tz/main.tex"}
    assert envelope.actor_role is Role.editor
    assert envelope.timeout_s == 600.0
    assert job.user_id == _USER
    assert job.max_attempts == 2


async def test__submit__staging_fails__failed_record_and_nothing_queued(rig: Rig) -> None:
    rig.uploader.error = ManifestFileTooLargeError("big.bin", 10, 5)
    hooks = Hooks()
    spec = rig.spec()

    rig.dispatcher.submit(spec, hooks)
    await _until(lambda: hooks.events == ["on_finished"])

    result, log = hooks.finished[0]
    assert result.status is JobStatus.failed
    assert result.error is not None
    assert (result.error.category, result.error.code) == (JobErrorCategory.invalid_input, "manifest_file_too_large")
    assert "big.bin" in log
    assert await rig.queue.get(spec.id) is None
    await _until(lambda: not rig.dispatcher.is_active(spec.id))


async def test__submit__unexpected_staging_error__failed_record(rig: Rig) -> None:
    rig.uploader.error = RuntimeError("boom")
    hooks = Hooks()

    rig.dispatcher.submit(rig.spec(), hooks)
    await _until(lambda: hooks.events == ["on_finished"])

    result, _ = hooks.finished[0]
    assert result.error is not None
    assert (result.error.category, result.error.code) == (JobErrorCategory.internal, "staging_failed")


async def test__submit__no_compile_record__job_is_cancelled_without_on_finished(rig: Rig) -> None:
    hooks = Hooks(started=False)
    spec = rig.spec()

    rig.dispatcher.submit(spec, hooks)
    await _until(lambda: rig.queue._jobs.get(spec.id) is not None)
    await rig.claim()
    await _until(lambda: not rig.dispatcher.is_active(spec.id))

    assert hooks.events == ["on_started"]
    job = await rig.queue.get(spec.id)
    assert job is not None
    assert job.cancel_requested


async def test__submit__newer_compile_of_same_document__replaces_queued_one(rig: Rig) -> None:
    first, second = Hooks(), Hooks()
    spec_a, spec_b = rig.spec(), rig.spec()

    rig.dispatcher.submit(spec_a, first)
    await _until(lambda: rig.queue._jobs.get(spec_a.id) is not None)
    rig.dispatcher.submit(spec_b, second)
    await _until(lambda: first.events == ["on_finished"])

    result, _ = first.finished[0]
    assert result.status is JobStatus.cancelled
    assert result.error is not None
    assert result.error.code == "superseded"
    assert second.events == []
    stored = await rig.queue.get(spec_b.id)
    assert stored is not None
    assert stored.state is JobState.queued


async def test__cancel__queued_compile__finishes_as_cancelled(rig: Rig) -> None:
    hooks = Hooks()
    spec = rig.spec()
    rig.dispatcher.submit(spec, hooks)
    await _until(lambda: rig.queue._jobs.get(spec.id) is not None)

    assert await rig.dispatcher.cancel(spec.id) is True
    await _until(lambda: hooks.events == ["on_finished"])

    result, _ = hooks.finished[0]
    assert result.status is JobStatus.cancelled
    assert isinstance(result.data, CompileResult)
    assert result.data.build_ok is False


async def test__cancel__during_staging__nothing_is_queued(rig: Rig) -> None:
    gate = asyncio.Event()
    original = rig.uploader.ensure

    async def slow(*args: object, **kwargs: object) -> list[ManifestFile]:
        await gate.wait()
        return await original(*args, **kwargs)  # type: ignore[arg-type]

    rig.uploader.ensure = slow  # type: ignore[method-assign]
    hooks = Hooks()
    spec = rig.spec()
    rig.dispatcher.submit(spec, hooks)
    await asyncio.sleep(0.02)

    assert await rig.dispatcher.cancel(spec.id) is True
    gate.set()
    await _until(lambda: hooks.events == ["on_finished"])

    assert hooks.finished[0][0].status is JobStatus.cancelled
    assert await rig.queue.get(spec.id) is None


async def test__cancel__unknown_job__returns_false(rig: Rig) -> None:
    assert await rig.dispatcher.cancel(uuid4()) is False


async def test__submit__runner_lost__failed_with_unavailable_error(rig: Rig) -> None:
    hooks = Hooks()
    spec = rig.spec()
    rig.dispatcher.submit(spec, hooks)
    await _until(lambda: rig.queue._jobs.get(spec.id) is not None)
    job = await rig.claim()
    await rig.queue.complete(job.id, job.attempt, JobStatus.failed, error_code="runner_lost")

    await _until(lambda: "on_finished" in hooks.events)

    result, _ = hooks.finished[0]
    assert result.status is JobStatus.failed
    assert result.error is not None
    assert (result.error.category, result.error.code) == (JobErrorCategory.unavailable, "runner_lost")


async def test__run__returns_the_runner_result(rig: Rig) -> None:
    spec = rig.spec(make_office_spec())

    task = asyncio.create_task(rig.dispatcher.run(spec, timeout_s=30))
    await _until(lambda: rig.queue._jobs.get(spec.id) is not None)
    job = await rig.claim()
    await rig.finish(job, make_office_result())
    result = await task

    assert result == make_office_result()
    assert not rig.dispatcher.is_active(spec.id)
    assert rig.uploader.calls[0][2] == ("tz/_custom/ТЗ.docx",)


async def test__run__caller_cancelled__cancels_the_queued_job(rig: Rig) -> None:
    spec = rig.spec(make_office_spec())

    task = asyncio.create_task(rig.dispatcher.run(spec))
    await _until(lambda: rig.queue._jobs.get(spec.id) is not None)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    stored = await rig.queue.get(spec.id)
    assert stored is not None
    assert stored.state is JobState.cancelled
    assert not rig.dispatcher.is_active(spec.id)


async def test__run__timeout__returns_timed_out_and_cancels(rig: Rig) -> None:
    spec = rig.spec(make_office_spec())

    result = await rig.dispatcher.run(spec, timeout_s=0.05)

    assert result.status is JobStatus.timed_out
    stored = await rig.queue.get(spec.id)
    assert stored is not None
    assert stored.state is JobState.cancelled


async def test__run__staging_error__returns_failed_result(rig: Rig) -> None:
    rig.uploader.error = ManifestFileTooLargeError("a.docx", 10, 5)

    result = await rig.dispatcher.run(rig.spec(make_office_spec()))

    assert result.status is JobStatus.failed
    assert result.error is not None
    assert result.error.code == "manifest_file_too_large"
    assert result.data is None


async def test__run__not_awaitable_kind__is_refused(rig: Rig) -> None:
    with pytest.raises(ValueError, match="cannot be awaited"):
        await rig.dispatcher.run(rig.spec(make_compile_spec()))


async def test__run__verify_job__stages_the_pdf_only(rig: Rig) -> None:
    spec = rig.spec(make_verify_spec())

    task = asyncio.create_task(rig.dispatcher.run(spec, timeout_s=30))
    await _until(lambda: rig.queue._jobs.get(spec.id) is not None)
    await rig.dispatcher.cancel(spec.id)
    result = await task

    assert result.status is JobStatus.cancelled
    assert rig.uploader.calls[0][2] == (make_verify_spec().payload.pdf.path,)  # type: ignore[attr-defined]


async def test__submit_detached__observer_gets_result_once(rig: Rig) -> None:
    spec = rig.spec(make_office_spec())
    seen: list[JobResult] = []

    class Observer:
        async def on_finished(self, spec: JobSpec, result: JobResult) -> None:
            seen.append(result)

    rig.dispatcher.submit_detached(spec, Observer())
    assert rig.dispatcher.is_active(spec.id)
    await _until(lambda: rig.queue._jobs.get(spec.id) is not None)
    job = await rig.claim()
    await rig.finish(job, make_office_result())
    await rig.dispatcher.drain_detached(timeout_s=5)

    assert seen == [make_office_result()]
    assert not rig.dispatcher.has_any_active()


async def test__submit_detached__compile_kind__is_refused(rig: Rig) -> None:
    with pytest.raises(ValueError, match="cannot run detached"):
        rig.dispatcher.submit_detached(rig.spec(make_compile_spec()))


async def test__drain_detached__unfinished_job__is_cancelled(rig: Rig) -> None:
    spec = rig.spec(make_office_spec())
    rig.dispatcher.submit_detached(spec)
    await _until(lambda: rig.queue._jobs.get(spec.id) is not None)

    await rig.dispatcher.drain_detached(timeout_s=0.02)

    stored = await rig.queue.get(spec.id)
    assert stored is not None
    assert stored.state is JobState.cancelled


async def test__activity__compile_blocks_its_folder_while_in_flight(rig: Rig, tmp_path: Path) -> None:
    spec = rig.spec()

    rig.dispatcher.submit(spec, Hooks())

    assert rig.dispatcher.has_any_active()
    assert rig.dispatcher.has_active_for_folder(rig.folder)
    assert not rig.dispatcher.has_active_for_folder(tmp_path / "other")
    assert JobKind.compile is spec.kind


async def test__submit__actor_is_not_a_user__failed_record(rig: Rig) -> None:
    hooks = Hooks()
    spec = replace(rig.spec(), actor=Actor.local())

    rig.dispatcher.submit(spec, hooks)
    await _until(lambda: hooks.events == ["on_finished"])

    assert hooks.finished[0][0].status is JobStatus.failed


async def test__submit__user_latex_passes_land_in_the_queued_payload(rig: Rig) -> None:
    class _Settings:
        async def get(self) -> dict[str, object]:
            return {"latex_passes": 9}

        async def save(self, settings: dict[str, object]) -> None: ...

    dispatcher = QueueJobDispatcher(
        rig.queue, rig.uploader, rig.runners, settings_repo=_Settings(), poll_interval_s=0.005
    )
    spec = rig.spec()

    dispatcher.submit(spec, Hooks())
    await _until(lambda: rig.queue._jobs.get(spec.id) is not None)

    job = await rig.claim()
    envelope = decode_envelope({**job.payload, "attempt": 1, "job_token": "t"})
    assert envelope.spec.payload.default_passes == 9  # type: ignore[attr-defined]


async def test__submit__no_user_latex_passes__template_value_stays(rig: Rig) -> None:
    class _Settings:
        async def get(self) -> dict[str, object]:
            return {}

        async def save(self, settings: dict[str, object]) -> None: ...

    dispatcher = QueueJobDispatcher(
        rig.queue, rig.uploader, rig.runners, settings_repo=_Settings(), poll_interval_s=0.005
    )
    spec = rig.spec()

    dispatcher.submit(spec, Hooks())
    await _until(lambda: rig.queue._jobs.get(spec.id) is not None)

    job = await rig.claim()
    envelope = decode_envelope({**job.payload, "attempt": 1, "job_token": "t"})
    assert envelope.spec.payload.default_passes == 5  # type: ignore[attr-defined]
