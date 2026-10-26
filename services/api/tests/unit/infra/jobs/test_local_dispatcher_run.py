"""LocalJobDispatcher.run: обработчик идёт в задаче вызывающего и отдаёт результат, а не исключение."""

from __future__ import annotations

import asyncio
import contextvars
from dataclasses import replace
from pathlib import Path

import pytest
import structlog
from hse_doc_studio.core.jobs.base import JobPayload, JobResultData
from hse_doc_studio.core.jobs.entities import JobSpec
from hse_doc_studio.core.jobs.enums import JobErrorCategory, JobKind, JobStatus
from hse_doc_studio.core.jobs.errors import JobFailure
from hse_doc_studio.core.jobs.office import OfficeConvertResult, OfficeConvertStatus
from hse_doc_studio.core.jobs.policy import JobKindPolicy
from hse_doc_studio.core.jobs.protocols import JobContext
from hse_doc_studio.core.jobs.registry import JobKindSpec, job_kind_spec
from hse_doc_studio.infra.jobs import local_dispatcher

from tests.unit.core.jobs.samples import JOB_ID, make_compile_spec, make_office_spec
from tests.unit.infra.jobs.dispatcher_helpers import FakeOfficeHandler, Rig, make_rig, wait_until

_REQUEST_ID: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="none")

_OK = OfficeConvertResult(status=OfficeConvertStatus.ok, pages=4)


def _rig_with(handler: FakeOfficeHandler, *, round_trip: bool = False) -> Rig:
    rig = make_rig(round_trip=round_trip)
    rig.handlers.register(JobKind.office_convert, handler)
    return rig


def _spec(tmp_path: Path) -> JobSpec:
    return make_office_spec(local_root=tmp_path)


async def test__dispatcher_run__runs_inline_in_caller_task_and_inherits_contextvars(tmp_path: Path) -> None:
    seen: list[tuple[asyncio.Task[object] | None, str]] = []

    async def body(payload: JobPayload, ctx: JobContext) -> JobResultData:
        seen.append((asyncio.current_task(), _REQUEST_ID.get()))
        return _OK

    rig = _rig_with(FakeOfficeHandler(body))
    _REQUEST_ID.set("req-1")

    result = await rig.dispatcher.run(_spec(tmp_path))

    assert result.status is JobStatus.succeeded
    assert result.data == _OK
    assert seen == [(asyncio.current_task(), "req-1")]


async def test__dispatcher_run__handler_gets_the_payload_and_a_context_over_local_root(tmp_path: Path) -> None:
    handler = FakeOfficeHandler()
    rig = _rig_with(handler)
    spec = _spec(tmp_path)

    await rig.dispatcher.run(spec)

    payload, ctx = handler.calls[0]
    assert payload == spec.payload
    assert (ctx.job_id, ctx.project_id, ctx.actor, ctx.locale) == (spec.id, spec.project_id, spec.actor, spec.locale)
    assert ctx.workspace == tmp_path
    assert ctx.outputs is not None


async def test__dispatcher_run__handler_raises__failed_result_not_exception_and_logged(tmp_path: Path) -> None:
    async def body(payload: JobPayload, ctx: JobContext) -> JobResultData:
        raise RuntimeError("converter exploded")

    rig = _rig_with(FakeOfficeHandler(body))

    with structlog.testing.capture_logs() as logs:
        result = await rig.dispatcher.run(_spec(tmp_path))

    assert result.status is JobStatus.failed
    assert result.error is not None
    assert (result.error.category, result.error.code) == (JobErrorCategory.internal, "handler_crashed")
    assert result.error.detail == "converter exploded"
    assert any(entry["event"] == "job handler crashed" and entry["log_level"] == "error" for entry in logs)


async def test__dispatcher_run__job_failure__error_code_preserved(tmp_path: Path) -> None:
    async def body(payload: JobPayload, ctx: JobContext) -> JobResultData:
        raise JobFailure.of(JobErrorCategory.invalid_input, "unknown_signature_format", "raw detail")

    rig = _rig_with(FakeOfficeHandler(body))

    result = await rig.dispatcher.run(_spec(tmp_path))

    assert result.status is JobStatus.failed
    assert result.data is None
    assert result.error is not None
    assert (result.error.category, result.error.code, result.error.detail) == (
        JobErrorCategory.invalid_input,
        "unknown_signature_format",
        "raw detail",
    )
    with pytest.raises(ValueError, match="raw detail"):
        result.raise_for_error()


async def test__dispatcher_run__caller_cancelled__cancellation_propagates(tmp_path: Path) -> None:
    started = asyncio.Event()

    async def body(payload: JobPayload, ctx: JobContext) -> JobResultData:
        started.set()
        await asyncio.Event().wait()
        return _OK

    rig = _rig_with(FakeOfficeHandler(body))
    task = asyncio.create_task(rig.dispatcher.run(_spec(tmp_path)))
    await started.wait()
    assert rig.dispatcher.is_active(JOB_ID)

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert not rig.dispatcher.is_active(JOB_ID)


async def test__dispatcher_run__explicit_timeout__timed_out_result(tmp_path: Path) -> None:
    async def body(payload: JobPayload, ctx: JobContext) -> JobResultData:
        await asyncio.Event().wait()
        return _OK

    rig = _rig_with(FakeOfficeHandler(body))

    result = await rig.dispatcher.run(_spec(tmp_path), timeout_s=0.01)

    assert result.status is JobStatus.timed_out
    assert result.error is not None
    assert result.error.code == "timed_out"
    assert not rig.dispatcher.is_active(JOB_ID)


async def test__dispatcher_run__handler_timeout_error_without_a_deadline__failed_not_timed_out(
    tmp_path: Path,
) -> None:
    async def body(payload: JobPayload, ctx: JobContext) -> JobResultData:
        raise TimeoutError("inner wait expired")

    rig = _rig_with(FakeOfficeHandler(body))

    result = await rig.dispatcher.run(_spec(tmp_path))

    assert result.status is JobStatus.failed
    assert result.error is not None
    assert result.error.code == "handler_crashed"


async def test__dispatcher_run__pack_policy_concurrency_one__second_call_waits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = job_kind_spec(JobKind.office_convert)
    serial = JobKindSpec(
        kind=base.kind,
        payload_cls=base.payload_cls,
        result_cls=base.result_cls,
        policy=JobKindPolicy(awaitable=True, embedded_concurrency=1),
    )
    monkeypatch.setattr(local_dispatcher, "job_kind_spec", lambda kind: serial)
    release = asyncio.Event()
    entered: list[int] = []

    async def body(payload: JobPayload, ctx: JobContext) -> JobResultData:
        entered.append(len(entered))
        await release.wait()
        return _OK

    rig = _rig_with(FakeOfficeHandler(body))
    first = asyncio.create_task(rig.dispatcher.run(_spec(tmp_path)))
    second = asyncio.create_task(rig.dispatcher.run(replace(_spec(tmp_path), id=JOB_ID.__class__(int=1))))
    await wait_until(lambda: len(entered) == 1)
    for _ in range(20):
        await asyncio.sleep(0)

    assert entered == [0]
    release.set()
    results = await asyncio.gather(first, second)

    assert entered == [0, 1]
    assert [r.status for r in results] == [JobStatus.succeeded, JobStatus.succeeded]


async def test__dispatcher_run__non_awaitable_kind__value_error(tmp_path: Path) -> None:
    rig = make_rig()

    with pytest.raises(ValueError, match="cannot be awaited"):
        await rig.dispatcher.run(make_compile_spec(local_root=tmp_path))


async def test__dispatcher_run__does_not_touch_compile_registry_or_has_any_active(tmp_path: Path) -> None:
    flags: list[bool] = []
    rig = make_rig()

    async def body(payload: JobPayload, ctx: JobContext) -> JobResultData:
        flags.extend(
            [
                rig.dispatcher.has_any_active(),
                rig.dispatcher.has_active_for_folder(tmp_path),
                rig.registry.get_meta(JOB_ID) is not None,
                rig.stream.has(JOB_ID),
            ]
        )
        return _OK

    rig.handlers.register(JobKind.office_convert, FakeOfficeHandler(body))

    await rig.dispatcher.run(_spec(tmp_path))

    assert flags == [False, False, False, False]


async def test__dispatcher_run__unknown_handler__clear_error(tmp_path: Path) -> None:
    rig = make_rig()

    with pytest.raises(ValueError, match="no handler registered for job kind office.convert"):
        await rig.dispatcher.run(_spec(tmp_path))


async def test__dispatcher_run__no_local_root__value_error() -> None:
    rig = _rig_with(FakeOfficeHandler())

    with pytest.raises(ValueError, match="no local_root"):
        await rig.dispatcher.run(make_office_spec())


async def test__dispatcher_run__round_trip_enabled__live_object_in_payload_raises_type_error(tmp_path: Path) -> None:
    handler = FakeOfficeHandler()
    rig = _rig_with(handler, round_trip=True)
    spec = _spec(tmp_path)
    live = replace(spec, payload=replace(spec.payload, output_path=tmp_path / "x.pdf"))  # type: ignore[type-var]

    with pytest.raises(TypeError, match="cannot be sent in a job"):
        await rig.dispatcher.run(live)

    assert handler.calls == []


async def test__dispatcher_run__round_trip_enabled__live_object_in_result_raises_type_error(tmp_path: Path) -> None:
    async def body(payload: JobPayload, ctx: JobContext) -> JobResultData:
        return OfficeConvertResult(status=OfficeConvertStatus.ok, detail=b"raw")  # type: ignore[arg-type]

    rig = _rig_with(FakeOfficeHandler(body), round_trip=True)

    with pytest.raises(TypeError, match="cannot be sent in a job"):
        await rig.dispatcher.run(_spec(tmp_path))


async def test__dispatcher_run__round_trip_enabled__handler_sees_an_equal_payload_and_the_local_root(
    tmp_path: Path,
) -> None:
    handler = FakeOfficeHandler()
    rig = _rig_with(handler, round_trip=True)
    spec = _spec(tmp_path)

    result = await rig.dispatcher.run(spec)

    payload, ctx = handler.calls[0]
    assert payload == spec.payload
    assert payload is not spec.payload
    assert ctx.workspace == tmp_path
    assert isinstance(result.data, OfficeConvertResult)
