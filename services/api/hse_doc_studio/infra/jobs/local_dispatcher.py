"""Диспетчер задач внутри процесса приложения.

Три режима: `submit` (compile, фоновая задача с живым логом и хуками записи),
`run` (ждём результат в задаче вызывающего) и `submit_detached` (фон без ожидания).
"""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import AbstractAsyncContextManager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog

from hse_doc_studio.core.events import IJobLogStream
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.core.jobs.codec import decode_result, decode_spec, encode_result, encode_spec
from hse_doc_studio.core.jobs.entities import CompileResult, JobResult, JobSpec, compile_payload_of
from hse_doc_studio.core.jobs.enums import JobErrorCategory, JobKind, JobStatus
from hse_doc_studio.core.jobs.errors import JobError, JobFailure
from hse_doc_studio.core.jobs.outputs import IJobOutputs
from hse_doc_studio.core.jobs.protocols import (
    ICompileJobRunner,
    IJobHandler,
    IJobHooks,
    IJobObserver,
    JobContext,
    JobRunContext,
)
from hse_doc_studio.core.jobs.registry import JobKindSpec, job_kind_spec
from hse_doc_studio.infra.compile.compile_runner import CompileRunner
from hse_doc_studio.infra.jobs.handler_registry import JobHandlerRegistry

logger = structlog.get_logger()

ERROR_CODE_HANDLER_CRASHED = "handler_crashed"
ERROR_CODE_COMPILE_CRASHED = "compile_crashed"
ERROR_CODE_TIMED_OUT = "timed_out"


class _CompileLogSink:
    """Лог сборки: строки копятся для итоговой записи и сразу уходят в шину."""

    def __init__(self, stream: IJobLogStream, job_id: UUID) -> None:
        self._stream = stream
        self._job_id = job_id
        self._lines: list[str] = []

    def emit(self, line: str) -> None:
        self._lines.append(line)
        self._stream.publish(self._job_id, line)

    def publish_only(self, line: str) -> None:
        self._stream.publish(self._job_id, line)

    def text(self) -> str:
        return "\n".join(self._lines)


class LocalJobDispatcher:
    """Выполняет задачи в процессе приложения; compile живёт в реестре CompileRunner."""

    def __init__(  # noqa: PLR0913
        self,
        compile_runner: ICompileJobRunner,
        handlers: JobHandlerRegistry,
        log_stream: IJobLogStream,
        compile_registry: CompileRunner,
        outputs: IJobOutputs,
        round_trip: bool = False,
    ) -> None:
        self._compile_runner = compile_runner
        self._handlers = handlers
        self._log_stream = log_stream
        self._compile_registry = compile_registry
        self._outputs = outputs
        self._round_trip = round_trip
        self._semaphores: dict[JobKind, asyncio.Semaphore] = {}
        # Идущие не-compile задачи; compile отслеживает его реестр.
        self._in_flight: dict[UUID, JobSpec] = {}
        self._detached: set[asyncio.Task[None]] = set()

    async def preflight(self, spec: JobSpec) -> None:
        if spec.kind is JobKind.compile:
            await self._compile_runner.preflight(spec)

    # --- compile ---

    def submit(self, spec: JobSpec, hooks: IJobHooks) -> None:
        payload = compile_payload_of(spec)
        project_folder = self._workspace_of(spec)
        spec = self._through_wire(spec)
        task = asyncio.create_task(self._drive_compile(spec, hooks))
        self._compile_registry.register(spec.id, task, project_folder, payload.doc_id)

    async def _drive_compile(self, spec: JobSpec, hooks: IJobHooks) -> None:
        set_interface_language(spec.locale.value)
        job_id = spec.id
        if not await hooks.on_started(spec):
            # Записи сборки нет: шину не закрываем, закрывать нечего.
            self._compile_registry.unregister(job_id)
            return

        # Шина закрывается ровно один раз и только ПОСЛЕ записи итоговой записи:
        # SSE `done` берёт статус из неё. Закрытие раньше (до проверок и до итога)
        # давало подписчику устаревший `running` и клиент зависал до сторожа.
        try:
            sink = _CompileLogSink(self._log_stream, job_id)
            ctx = JobRunContext(
                log=sink,
                workspace=self._workspace_of(spec),
                on_process=lambda process: self._compile_registry.set_process(job_id, process),
            )
            result = await self._build(spec, ctx, sink)
            await hooks.on_finished(spec, self._result_through_wire(spec, result), sink.text())
        finally:
            self._log_stream.close(job_id)
            self._compile_registry.unregister(job_id)

    async def _build(self, spec: JobSpec, ctx: JobRunContext, sink: _CompileLogSink) -> JobResult:
        try:
            outcome = await self._compile_runner.run_build(spec, ctx)
        except asyncio.CancelledError:
            sink.emit("[cancelled] build cancelled by user")
            return self._unfinished(JobStatus.cancelled)
        except Exception as exc:
            sink.emit(f"[error] compile task crashed: {exc}")
            logger.exception("compile task crashed", compile_id=str(spec.id))
            return self._unfinished(
                JobStatus.failed, JobError(JobErrorCategory.internal, ERROR_CODE_COMPILE_CRASHED, str(exc))
            )
        # Проверки идут вне охраны сборки: отмена или сбой в них оставляют запись
        # «идёт», а исключение уходит наружу без on_finished, как в исходном коде.
        return await self._compile_runner.run_post(spec, ctx, outcome)

    @staticmethod
    def _unfinished(status: JobStatus, error: JobError | None = None) -> JobResult:
        return JobResult(
            status=status,
            data=CompileResult(build_ok=False, finished_at=datetime.now(tz=timezone.utc)),
            error=error,
        )

    async def cancel(self, job_id: UUID) -> bool:
        return await self._compile_registry.cancel(job_id)

    # --- run / detached ---

    async def run(self, spec: JobSpec, *, timeout_s: float | None = None) -> JobResult:
        if not job_kind_spec(spec.kind).policy.awaitable:
            raise ValueError(f"job kind {spec.kind} cannot be awaited")
        return await self._execute(spec, timeout_s)

    def submit_detached(self, spec: JobSpec, observer: IJobObserver | None = None) -> None:
        if not job_kind_spec(spec.kind).policy.detachable:
            raise ValueError(f"job kind {spec.kind} cannot run detached")
        # Отсутствие обработчика и цикла событий всплывает здесь, а не внутри фона.
        self._handlers.get(spec.kind)
        loop = asyncio.get_running_loop()
        # Задача создаётся в контексте вызывающего: язык и актор запроса остаются при ней.
        task = loop.create_task(self._run_detached(spec, observer))
        self._detached.add(task)
        # Задача считается идущей с постановки, даже если отменена до первого шага.
        self._in_flight[spec.id] = spec
        task.add_done_callback(lambda done: self._finish_detached(spec.id, done))

    def _finish_detached(self, job_id: UUID, task: asyncio.Task[None]) -> None:
        self._detached.discard(task)
        self._in_flight.pop(job_id, None)

    async def _run_detached(self, spec: JobSpec, observer: IJobObserver | None) -> None:
        try:
            result = await self._execute(spec, None)
        except Exception:
            logger.exception("detached job failed", job_id=str(spec.id), kind=str(spec.kind))
            return
        if observer is None:
            return
        try:
            await observer.on_finished(spec, result)
        except Exception:
            logger.exception("job observer failed", job_id=str(spec.id), kind=str(spec.kind))

    async def drain_detached(self, timeout_s: float) -> None:
        pending = set(self._detached)
        if not pending:
            return
        _, unfinished = await asyncio.wait(pending, timeout=timeout_s)
        for task in unfinished:
            task.cancel()
        if unfinished:
            await asyncio.gather(*unfinished, return_exceptions=True)

    async def _execute(self, spec: JobSpec, timeout_s: float | None) -> JobResult:
        kind_spec = job_kind_spec(spec.kind)
        handler = self._handlers.get(spec.kind)
        spec = self._through_wire(spec)
        ctx = JobContext(
            job_id=spec.id,
            project_id=spec.project_id,
            actor=spec.actor,
            locale=spec.locale,
            workspace=self._workspace_of(spec),
            outputs=self._outputs,
        )
        self._in_flight[spec.id] = spec
        try:
            result = await self._invoke(handler, spec, ctx, kind_spec, timeout_s)
        finally:
            self._in_flight.pop(spec.id, None)
        return self._result_through_wire(spec, result)

    async def _invoke(
        self,
        handler: IJobHandler[Any],
        spec: JobSpec,
        ctx: JobContext,
        kind_spec: JobKindSpec,
        timeout_s: float | None,
    ) -> JobResult:
        # Обработчик идёт прямо в задаче вызывающего, без create_task: так он видит те же
        # contextvars, а отмена вызывающего отменяет и задачу.
        deadline = asyncio.timeout(timeout_s)
        try:
            async with deadline, self._slot(kind_spec):
                data = await handler.handle(spec.payload, ctx)
        except JobFailure as failure:
            return JobResult(status=JobStatus.failed, error=failure.error)
        except TimeoutError as exc:
            if deadline.expired():
                error = JobError(JobErrorCategory.internal, ERROR_CODE_TIMED_OUT, f"timed out after {timeout_s} s")
                return JobResult(status=JobStatus.timed_out, error=error)
            return self._handler_crashed(spec, exc)
        except Exception as exc:
            return self._handler_crashed(spec, exc)
        return JobResult(status=JobStatus.succeeded, data=data)

    @staticmethod
    def _handler_crashed(spec: JobSpec, exc: Exception) -> JobResult:
        logger.exception("job handler crashed", job_id=str(spec.id), kind=str(spec.kind))
        error = JobError(JobErrorCategory.internal, ERROR_CODE_HANDLER_CRASHED, str(exc))
        return JobResult(status=JobStatus.failed, error=error)

    def _slot(self, kind_spec: JobKindSpec) -> AbstractAsyncContextManager[object]:
        limit = kind_spec.policy.embedded_concurrency
        if limit is None:
            return contextlib.nullcontext()
        return self._semaphores.setdefault(kind_spec.kind, asyncio.Semaphore(limit))

    # --- activity ---

    def is_active(self, job_id: UUID) -> bool:
        return self._compile_registry.is_running(job_id) or job_id in self._in_flight

    def has_any_active(self) -> bool:
        return self._compile_registry.has_any_active() or any(
            job_kind_spec(spec.kind).policy.counts_as_active for spec in self._in_flight.values()
        )

    def has_active_for_folder(self, folder: Path) -> bool:
        if self._compile_registry.has_active_for_folder(folder):
            return True
        return any(
            job_kind_spec(spec.kind).policy.blocks_folder_ops
            and spec.local_root is not None
            and _same_folder(spec.local_root, folder)
            for spec in self._in_flight.values()
        )

    # --- helpers ---

    @staticmethod
    def _workspace_of(spec: JobSpec) -> Path:
        if spec.local_root is None:
            raise ValueError(f"job {spec.id} has no local_root")
        return spec.local_root

    def _through_wire(self, spec: JobSpec) -> JobSpec:
        """С включённой проверкой пропускает задачу через кодек; `local_root` в конверт не входит."""
        if not self._round_trip:
            return spec
        return replace(decode_spec(encode_spec(spec)), local_root=spec.local_root)

    def _result_through_wire(self, spec: JobSpec, result: JobResult) -> JobResult:
        if not self._round_trip:
            return result
        return decode_result(spec.kind, encode_result(result))


def _same_folder(left: Path, right: Path) -> bool:
    with contextlib.suppress(OSError):
        return left.resolve() == right.resolve()
    return left == right
