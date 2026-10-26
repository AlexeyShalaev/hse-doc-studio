"""Общие заглушки для тестов LocalJobDispatcher."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from hse_doc_studio.core.jobs.base import JobPayload, JobResultData
from hse_doc_studio.core.jobs.entities import BuildOutcome, CompileResult, JobResult, JobSpec
from hse_doc_studio.core.jobs.enums import JobStatus
from hse_doc_studio.core.jobs.office import OfficeConvertResult, OfficeConvertStatus
from hse_doc_studio.core.jobs.protocols import JobContext, JobRunContext
from hse_doc_studio.infra.compile.compile_runner import CompileRunner
from hse_doc_studio.infra.compile.log_bus import CompileLogBus
from hse_doc_studio.infra.jobs.handler_registry import JobHandlerRegistry
from hse_doc_studio.infra.jobs.local_dispatcher import LocalJobDispatcher
from hse_doc_studio.infra.jobs.outputs import LocalJobOutputs

_NOW = datetime(2026, 10, 26, 9, 30, tzinfo=timezone.utc)


class RecordingLogBus(CompileLogBus):
    """Шина, которая пишет момент закрытия в общий журнал событий."""

    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self._events = events

    def close(self, compile_id: UUID) -> None:
        self._events.append("close")
        super().close(compile_id)


class FakeCompileRunner:
    """Раннер с настраиваемым поведением фаз; каждый вызов попадает в журнал."""

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.build: Callable[[JobSpec, JobRunContext], Awaitable[None]] | None = None
        self.post: Callable[[], Awaitable[None]] | None = None
        self.specs: list[JobSpec] = []

    async def preflight(self, spec: JobSpec) -> None:
        self.events.append("preflight")

    async def run_build(self, spec: JobSpec, ctx: JobRunContext) -> BuildOutcome:
        self.events.append("run_build")
        self.specs.append(spec)
        if self.build is not None:
            await self.build(spec, ctx)
        return BuildOutcome(success=True, status=JobStatus.succeeded, finished_at=_NOW, pages=3)

    async def run_post(self, spec: JobSpec, ctx: JobRunContext, outcome: BuildOutcome) -> JobResult:
        self.events.append("run_post")
        if self.post is not None:
            await self.post()
        return JobResult(
            status=outcome.status,
            data=CompileResult(build_ok=outcome.success, pages=outcome.pages, finished_at=outcome.finished_at),
        )


class FakeHooks:
    def __init__(self, events: list[str], *, started: bool = True) -> None:
        self.events = events
        self.started = started
        self.finished: list[tuple[JobResult, str]] = []

    async def on_started(self, spec: JobSpec) -> bool:
        self.events.append("on_started")
        return self.started

    async def on_finished(self, spec: JobSpec, result: JobResult, log: str) -> None:
        self.events.append("on_finished")
        # Пока хуки пишут итог, шина обязана оставаться открытой.
        for _ in range(3):
            await asyncio.sleep(0)
        self.finished.append((result, log))
        self.events.append("on_finished_done")


class FakeProcess:
    """Подпроцесс сборки: terminate завершает его, kill не нужен."""

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.returncode: int | None = None
        self._exited = asyncio.Event()

    def terminate(self) -> None:
        self.events.append("terminate")
        self.returncode = -15
        self._exited.set()

    def kill(self) -> None:
        self.events.append("kill")
        self.returncode = -9
        self._exited.set()

    async def wait(self) -> int:
        await self._exited.wait()
        assert self.returncode is not None
        return self.returncode


@dataclass
class FakeOfficeHandler:
    """Обработчик office.convert с настраиваемым телом."""

    body: Callable[[JobPayload, JobContext], Awaitable[JobResultData]] | None = None
    calls: list[tuple[JobPayload, JobContext]] = field(default_factory=list)

    async def handle(self, payload: Any, ctx: JobContext) -> JobResultData:
        self.calls.append((payload, ctx))
        if self.body is not None:
            return await self.body(payload, ctx)
        return OfficeConvertResult(status=OfficeConvertStatus.unavailable, reason_code="converter_unavailable")


@dataclass
class Rig:
    dispatcher: LocalJobDispatcher
    runner: FakeCompileRunner
    registry: CompileRunner
    stream: RecordingLogBus
    handlers: JobHandlerRegistry
    events: list[str]


def make_rig(*, round_trip: bool = False) -> Rig:
    events: list[str] = []
    runner = FakeCompileRunner(events)
    registry = CompileRunner()
    stream = RecordingLogBus(events)
    handlers = JobHandlerRegistry()
    dispatcher = LocalJobDispatcher(
        compile_runner=runner,
        handlers=handlers,
        log_stream=stream,
        compile_registry=registry,
        outputs=LocalJobOutputs(),
        round_trip=round_trip,
    )
    return Rig(dispatcher, runner, registry, stream, handlers, events)


async def wait_until(condition: Callable[[], bool], *, limit: int = 2000) -> None:
    """Даёт циклу событий крутиться, пока условие не выполнится; без таймеров, на событиях."""
    for _ in range(limit):
        if condition():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition was not reached")
