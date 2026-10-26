"""LocalJobDispatcher, режим compile: порядок фаз и их охрана повторяют _run_compile_task."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.i18n import current_interface_language, set_interface_language
from hse_doc_studio.core.jobs.entities import CompileResult, JobResult, JobSpec
from hse_doc_studio.core.jobs.enums import JobErrorCategory, JobStatus
from hse_doc_studio.core.jobs.protocols import JobRunContext

from tests.unit.core.jobs.samples import JOB_ID, make_compile_spec, make_office_spec
from tests.unit.infra.jobs.dispatcher_helpers import FakeHooks, FakeProcess, Rig, make_rig, wait_until


def _spec(tmp_path: Path) -> JobSpec:
    return make_compile_spec(local_root=tmp_path)


async def _idle(rig: Rig) -> None:
    await wait_until(lambda: not rig.dispatcher.is_active(JOB_ID))


async def test__dispatcher_submit__returns_before_the_task_runs_and_registers_it(tmp_path: Path) -> None:
    rig = make_rig()

    rig.dispatcher.submit(_spec(tmp_path), FakeHooks(rig.events))

    assert rig.events == []
    assert rig.dispatcher.is_active(JOB_ID)
    assert rig.registry.get_meta(JOB_ID) == (tmp_path, "tz")
    await _idle(rig)


async def test__dispatcher_submit__phases_run_in_order_and_the_stream_closes_after_the_final_record(
    tmp_path: Path,
) -> None:
    rig = make_rig()

    rig.dispatcher.submit(_spec(tmp_path), FakeHooks(rig.events))
    await _idle(rig)

    assert rig.events == ["on_started", "run_build", "run_post", "on_finished", "on_finished_done", "close"]
    assert not rig.registry.is_running(JOB_ID)


async def test__dispatcher_submit__on_started_false__unregisters_without_closing_the_stream(tmp_path: Path) -> None:
    rig = make_rig()

    rig.dispatcher.submit(_spec(tmp_path), FakeHooks(rig.events, started=False))
    await _idle(rig)

    assert rig.events == ["on_started"]
    assert rig.registry.get_meta(JOB_ID) is None


async def test__dispatcher_submit__log_lines_reach_the_record_log_and_the_stream(tmp_path: Path) -> None:
    rig = make_rig()
    hooks = FakeHooks(rig.events)

    async def build(spec: JobSpec, ctx: JobRunContext) -> None:
        ctx.log.emit("line one")
        ctx.log.publish_only("[checks] only on the stream")
        ctx.log.emit("line two")
        assert ctx.log.text() == "line one\nline two"
        assert ctx.workspace == tmp_path

    rig.runner.build = build
    rig.dispatcher.submit(_spec(tmp_path), hooks)
    await _idle(rig)

    assert hooks.finished[0][1] == "line one\nline two"
    streamed = [line async for line in rig.stream.subscribe(JOB_ID)]
    assert streamed == ["line one", "[checks] only on the stream", "line two"]


async def test__dispatcher_submit__success__result_carries_the_compile_data(tmp_path: Path) -> None:
    rig = make_rig()
    hooks = FakeHooks(rig.events)

    rig.dispatcher.submit(_spec(tmp_path), hooks)
    await _idle(rig)

    result, _ = hooks.finished[0]
    assert result.status is JobStatus.succeeded
    assert result.data_as(CompileResult).pages == 3


async def test__dispatcher_submit__cancelled_in_build__cancelled_result_and_log_line(tmp_path: Path) -> None:
    rig = make_rig()
    hooks = FakeHooks(rig.events)

    async def build(spec: JobSpec, ctx: JobRunContext) -> None:
        raise asyncio.CancelledError

    rig.runner.build = build
    rig.dispatcher.submit(_spec(tmp_path), hooks)
    await _idle(rig)

    result, log = hooks.finished[0]
    assert result.status is JobStatus.cancelled
    assert result.error is None
    assert not result.data_as(CompileResult).build_ok
    assert log == "[cancelled] build cancelled by user"
    assert "run_post" not in rig.events
    assert rig.events[-1] == "close"


async def test__dispatcher_submit__exception_in_build__failed_result_and_crash_line(tmp_path: Path) -> None:
    rig = make_rig()
    hooks = FakeHooks(rig.events)

    async def build(spec: JobSpec, ctx: JobRunContext) -> None:
        ctx.log.emit("before")
        raise RuntimeError("boom")

    rig.runner.build = build
    rig.dispatcher.submit(_spec(tmp_path), hooks)
    await _idle(rig)

    result, log = hooks.finished[0]
    assert result.status is JobStatus.failed
    assert result.error is not None
    assert result.error.category is JobErrorCategory.internal
    assert result.error.detail == "boom"
    assert log == "before\n[error] compile task crashed: boom"
    assert "run_post" not in rig.events
    assert rig.events[-1] == "close"


async def test__dispatcher_submit__exception_in_post__propagates_without_on_finished_but_still_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig()
    tasks: list[asyncio.Task[None]] = []
    real_create_task = asyncio.create_task

    def recording_create_task(coro, **kwargs):  # type: ignore[no-untyped-def]
        task = real_create_task(coro, **kwargs)
        tasks.append(task)
        return task

    async def post() -> None:
        raise RuntimeError("checks blew up")

    rig.runner.post = post
    monkeypatch.setattr(asyncio, "create_task", recording_create_task)
    rig.dispatcher.submit(_spec(tmp_path), FakeHooks(rig.events))

    with pytest.raises(RuntimeError, match="checks blew up"):
        await tasks[0]

    assert rig.events == ["on_started", "run_build", "run_post", "close"]
    assert rig.registry.get_meta(JOB_ID) is None


async def test__dispatcher_cancel__terminates_the_process_before_cancelling_the_task(tmp_path: Path) -> None:
    rig = make_rig()
    hooks = FakeHooks(rig.events)
    process = FakeProcess(rig.events)
    started = asyncio.Event()

    async def build(spec: JobSpec, ctx: JobRunContext) -> None:
        ctx.on_process(process)
        started.set()
        await asyncio.Event().wait()

    rig.runner.build = build
    rig.dispatcher.submit(_spec(tmp_path), hooks)
    await started.wait()

    assert await rig.dispatcher.cancel(JOB_ID) is True
    await _idle(rig)

    assert rig.events.index("terminate") < rig.events.index("on_finished")
    assert hooks.finished[0][0].status is JobStatus.cancelled


async def test__dispatcher_cancel__unknown_job__false() -> None:
    assert await make_rig().dispatcher.cancel(JOB_ID) is False


async def test__dispatcher_activity__true_from_submit_until_the_task_finishes(tmp_path: Path) -> None:
    rig = make_rig()
    release = asyncio.Event()

    async def build(spec: JobSpec, ctx: JobRunContext) -> None:
        await release.wait()

    rig.runner.build = build
    assert not rig.dispatcher.has_any_active()

    rig.dispatcher.submit(_spec(tmp_path), FakeHooks(rig.events))

    assert rig.dispatcher.is_active(JOB_ID)
    assert rig.dispatcher.has_any_active()
    assert rig.dispatcher.has_active_for_folder(tmp_path)
    assert not rig.dispatcher.has_active_for_folder(tmp_path / "other")
    release.set()
    await _idle(rig)
    assert not rig.dispatcher.has_any_active()
    assert not rig.dispatcher.has_active_for_folder(tmp_path)


async def test__dispatcher_submit__locale__task_runs_under_the_spec_language(tmp_path: Path) -> None:
    rig = make_rig()
    seen: list[Lang] = []

    async def build(spec: JobSpec, ctx: JobRunContext) -> None:
        seen.append(current_interface_language())

    rig.runner.build = build
    set_interface_language("ru")
    try:
        rig.dispatcher.submit(_spec(tmp_path), FakeHooks(rig.events))
        await _idle(rig)
        assert current_interface_language() is Lang.ru
    finally:
        set_interface_language(None)

    assert seen == [Lang.en]


async def test__dispatcher_submit__round_trip__runner_gets_an_equal_spec_with_local_root(tmp_path: Path) -> None:
    rig = make_rig(round_trip=True)
    spec = _spec(tmp_path)

    rig.dispatcher.submit(spec, FakeHooks(rig.events))
    await _idle(rig)

    assert rig.runner.specs == [spec]
    assert rig.runner.specs[0].local_root == tmp_path


async def test__dispatcher_submit__round_trip_result__hooks_get_a_decoded_result(tmp_path: Path) -> None:
    rig = make_rig(round_trip=True)
    hooks = FakeHooks(rig.events)

    rig.dispatcher.submit(_spec(tmp_path), hooks)
    await _idle(rig)

    result, _ = hooks.finished[0]
    assert isinstance(result, JobResult)
    assert result.data_as(CompileResult).pages == 3


async def test__dispatcher_submit__not_a_compile_spec__type_error(tmp_path: Path) -> None:
    rig = make_rig()

    with pytest.raises(TypeError, match="not a compile job"):
        rig.dispatcher.submit(make_office_spec(local_root=tmp_path), FakeHooks(rig.events))

    assert rig.events == []


async def test__dispatcher_submit__no_local_root__value_error() -> None:
    rig = make_rig()

    with pytest.raises(ValueError, match="no local_root"):
        rig.dispatcher.submit(make_compile_spec(), FakeHooks(rig.events))


async def test__dispatcher_preflight__delegates_for_compile_and_is_a_noop_for_other_kinds(tmp_path: Path) -> None:
    rig = make_rig()

    await rig.dispatcher.preflight(_spec(tmp_path))
    await rig.dispatcher.preflight(make_office_spec(local_root=tmp_path))

    assert rig.events == ["preflight"]
