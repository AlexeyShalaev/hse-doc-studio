"""QueueJobDispatcher: лог раннера попадает в запись сборки и в живой поток, упавшая сборка не остаётся без лога."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from hse_doc_studio.core.compile.failure import failure_message
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.jobs.codec import encode_result
from hse_doc_studio.core.jobs.entities import CompileResult, JobResult
from hse_doc_studio.core.jobs.enums import JobErrorCategory, JobStatus
from hse_doc_studio.core.jobs.errors import JobError
from hse_doc_studio.infra.compile.log_bus import CompileLogBus
from hse_doc_studio.infra.jobs.queue_dispatcher import QueueJobDispatcher
from hse_doc_studio.infra.jobs.storage_fs import FsJobLogSink

from tests.fakes.job_queue import InMemoryJobQueue
from tests.fakes.runners import InMemoryRunnerRepository
from tests.unit.infra.jobs.test_queue_dispatcher import FakeUploader, Hooks, Rig, _until

pytestmark = pytest.mark.asyncio


@pytest.fixture
def logs(tmp_path: Path) -> FsJobLogSink:
    return FsJobLogSink(tmp_path / "jobs")


@pytest.fixture
def bus() -> CompileLogBus:
    return CompileLogBus()


@pytest.fixture
def rig(tmp_path: Path, logs: FsJobLogSink, bus: CompileLogBus) -> Rig:
    folder = tmp_path / "project"
    (folder / "tz").mkdir(parents=True)
    (folder / "tz" / "main.tex").write_text("x", encoding="utf-8", newline="\n")
    queue = InMemoryJobQueue()
    runners = InMemoryRunnerRepository()
    uploader = FakeUploader()
    dispatcher = QueueJobDispatcher(queue, uploader, runners, poll_interval_s=0.005, log_reader=logs, log_stream=bus)
    return Rig(dispatcher, queue, runners, uploader, folder)


async def test__failed_build__runner_log_reaches_on_finished(rig: Rig, logs: FsJobLogSink) -> None:
    hooks = Hooks()
    spec = rig.spec()
    rig.dispatcher.submit(spec, hooks)
    await _until(lambda: rig.queue._jobs.get(spec.id) is not None)
    job = await rig.claim()
    await _until(lambda: hooks.events == ["on_started"])
    await logs.append(spec.id, job.attempt, 0, ["! Undefined control sequence.", "l.12 \\foo"])

    result = JobResult(status=JobStatus.failed, data=CompileResult(build_ok=False))
    await rig.finish(job, result, JobStatus.failed)
    await _until(lambda: "on_finished" in hooks.events)

    _result, log = hooks.finished[0]
    assert log == "! Undefined control sequence.\nl.12 \\foo\n"


async def test__runner_without_log__on_finished_gets_empty_string(rig: Rig) -> None:
    hooks = Hooks()
    spec = rig.spec()
    rig.dispatcher.submit(spec, hooks)
    await _until(lambda: rig.queue._jobs.get(spec.id) is not None)
    job = await rig.claim()
    error = JobError(JobErrorCategory.unavailable, "image_missing", "texlive")
    await rig.finish(job, JobResult(status=JobStatus.failed, error=error), JobStatus.failed)
    await _until(lambda: "on_finished" in hooks.events)

    result, log = hooks.finished[0]
    assert (result.error.code if result.error else None, log) == ("image_missing", "")


async def test__running_build__new_runner_lines_are_published_live_and_bus_closes_after(
    rig: Rig, logs: FsJobLogSink, bus: CompileLogBus
) -> None:
    hooks = Hooks()
    spec = rig.spec()
    rig.dispatcher.submit(spec, hooks)
    await _until(lambda: rig.queue._jobs.get(spec.id) is not None)
    job = await rig.claim()
    await logs.append(spec.id, job.attempt, 0, ["first"])
    await _until(lambda: bus.has(spec.id))
    await logs.append(spec.id, job.attempt, 1, ["second"])

    await rig.finish(job, JobResult(status=JobStatus.succeeded, data=CompileResult(build_ok=True)))
    await _until(lambda: "on_finished" in hooks.events)
    await asyncio.sleep(0.05)

    assert [line async for line in bus.subscribe(spec.id)] == ["first", "second"]


async def test__log_reader_crashes__finish_still_happens_with_empty_log(rig: Rig, logs: FsJobLogSink) -> None:
    async def boom(*_a: object, **_k: object) -> str:
        raise OSError("disk")

    logs.read = boom  # type: ignore[method-assign]
    hooks = Hooks()
    spec = rig.spec()
    rig.dispatcher.submit(spec, hooks)
    await _until(lambda: rig.queue._jobs.get(spec.id) is not None)
    job = await rig.claim()
    await rig.finish(job, JobResult(status=JobStatus.failed), JobStatus.failed)
    await _until(lambda: "on_finished" in hooks.events)

    assert hooks.finished[0][1] == ""


def test__failure_catalog__every_known_code_has_both_languages() -> None:
    for code in ("image_missing", "docker_unavailable", "timed_out", "disk_full", "storage_unreachable", "no_runners"):
        assert failure_message(code, Lang.ru) != failure_message("unknown", Lang.ru)
        assert failure_message(code, Lang.en) != failure_message(code, Lang.ru)
    assert failure_message("something_new", Lang.en) == failure_message("unknown", Lang.en)


def test__encode_result_roundtrip_keeps_error_detail() -> None:
    error = JobError(JobErrorCategory.unavailable, "storage_unreachable", "connect refused")
    assert encode_result(JobResult(status=JobStatus.failed, error=error))["error"]["detail"] == "connect refused"
