"""LocalJobDispatcher.submit_detached и drain_detached: фон без ожидания."""

from __future__ import annotations

import asyncio
import gc
from pathlib import Path

import pytest
import structlog
from hse_doc_studio.core.jobs.base import JobPayload, JobResultData
from hse_doc_studio.core.jobs.entities import JobResult, JobSpec
from hse_doc_studio.core.jobs.enums import JobKind, JobStatus
from hse_doc_studio.core.jobs.office import OfficeConvertResult, OfficeConvertStatus
from hse_doc_studio.core.jobs.protocols import JobContext

from tests.unit.core.jobs.samples import JOB_ID, make_compile_spec, make_office_spec
from tests.unit.infra.jobs.dispatcher_helpers import FakeOfficeHandler, Rig, make_rig, wait_until

_OK = OfficeConvertResult(status=OfficeConvertStatus.ok, pages=4)


class RecordingObserver:
    def __init__(self, *, fails: bool = False) -> None:
        self.fails = fails
        self.results: list[tuple[JobSpec, JobResult]] = []

    async def on_finished(self, spec: JobSpec, result: JobResult) -> None:
        self.results.append((spec, result))
        if self.fails:
            raise RuntimeError("observer broke")


def _rig_with(handler: FakeOfficeHandler) -> Rig:
    rig = make_rig()
    rig.handlers.register(JobKind.office_convert, handler)
    return rig


def _spec(tmp_path: Path) -> JobSpec:
    return make_office_spec(local_root=tmp_path)


async def test__dispatcher_detached__keeps_strong_ref_swallows_observer_exception_not_counted_active(
    tmp_path: Path,
) -> None:
    release = asyncio.Event()
    observer = RecordingObserver(fails=True)

    async def body(payload: JobPayload, ctx: JobContext) -> JobResultData:
        await release.wait()
        return _OK

    rig = _rig_with(FakeOfficeHandler(body))

    with structlog.testing.capture_logs() as logs:
        rig.dispatcher.submit_detached(_spec(tmp_path), observer)
        # Задачу никто не держит снаружи: пока диспетчер хранит ссылку, её не соберёт сборщик.
        gc.collect()
        assert rig.dispatcher.is_active(JOB_ID)
        assert not rig.dispatcher.has_any_active()
        assert not rig.dispatcher.has_active_for_folder(tmp_path)
        release.set()
        await wait_until(lambda: bool(observer.results))
        await wait_until(lambda: not rig.dispatcher.is_active(JOB_ID))

    assert observer.results[0][1].status is JobStatus.succeeded
    assert any(entry["event"] == "job observer failed" for entry in logs)
    assert not rig.registry.has_any_active()
    await rig.dispatcher.drain_detached(1.0)


async def test__dispatcher_detached__handler_failure__observer_gets_the_failed_result(tmp_path: Path) -> None:
    observer = RecordingObserver()

    async def body(payload: JobPayload, ctx: JobContext) -> JobResultData:
        raise RuntimeError("converter exploded")

    rig = _rig_with(FakeOfficeHandler(body))

    rig.dispatcher.submit_detached(_spec(tmp_path), observer)
    await wait_until(lambda: bool(observer.results))

    assert observer.results[0][1].status is JobStatus.failed
    assert observer.results[0][1].error is not None
    assert observer.results[0][1].error.code == "handler_crashed"


async def test__dispatcher_detached__without_observer__runs_the_handler(tmp_path: Path) -> None:
    handler = FakeOfficeHandler()
    rig = _rig_with(handler)

    rig.dispatcher.submit_detached(_spec(tmp_path))
    await rig.dispatcher.drain_detached(1.0)

    assert len(handler.calls) == 1


async def test__dispatcher_detached__task_is_created_in_the_callers_context(tmp_path: Path) -> None:
    import contextvars

    var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="none")
    seen: list[str] = []

    async def body(payload: JobPayload, ctx: JobContext) -> JobResultData:
        seen.append(var.get())
        return _OK

    rig = _rig_with(FakeOfficeHandler(body))
    var.set("req-7")

    rig.dispatcher.submit_detached(_spec(tmp_path))
    await rig.dispatcher.drain_detached(1.0)

    assert seen == ["req-7"]


async def test__dispatcher_detached__drain_waits_then_cancels(tmp_path: Path) -> None:
    finished = asyncio.Event()
    cancelled: list[bool] = []
    observer = RecordingObserver()

    async def quick(payload: JobPayload, ctx: JobContext) -> JobResultData:
        await finished.wait()
        return _OK

    async def hanging(payload: JobPayload, ctx: JobContext) -> JobResultData:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.append(True)
            raise
        return _OK

    rig = _rig_with(FakeOfficeHandler(quick))
    rig.dispatcher.submit_detached(_spec(tmp_path), observer)
    drain = asyncio.create_task(rig.dispatcher.drain_detached(30.0))
    await asyncio.sleep(0)
    assert not drain.done()
    finished.set()
    await drain
    assert [r.status for _, r in observer.results] == [JobStatus.succeeded]

    stuck_rig = _rig_with(FakeOfficeHandler(hanging))
    stuck_observer = RecordingObserver()
    stuck_rig.dispatcher.submit_detached(_spec(tmp_path), stuck_observer)
    await asyncio.sleep(0)

    await stuck_rig.dispatcher.drain_detached(0.01)

    assert cancelled == [True]
    assert stuck_observer.results == []
    assert not stuck_rig.dispatcher.is_active(JOB_ID)


async def test__dispatcher_detached__drain_with_nothing_running__returns() -> None:
    await make_rig().dispatcher.drain_detached(0.01)


async def test__dispatcher_detached__non_detachable_kind__value_error(tmp_path: Path) -> None:
    rig = make_rig()

    with pytest.raises(ValueError, match="cannot run detached"):
        rig.dispatcher.submit_detached(make_compile_spec(local_root=tmp_path))


async def test__dispatcher_detached__unknown_handler__clear_error_at_submit(tmp_path: Path) -> None:
    rig = make_rig()

    with pytest.raises(ValueError, match="no handler registered"):
        rig.dispatcher.submit_detached(_spec(tmp_path))


def test__dispatcher_detached__no_running_loop__runtime_error(tmp_path: Path) -> None:
    rig = _rig_with(FakeOfficeHandler())

    with pytest.raises(RuntimeError, match="no running event loop"):
        rig.dispatcher.submit_detached(_spec(tmp_path))
