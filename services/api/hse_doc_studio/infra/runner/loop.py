from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from hse_doc_studio.core.jobs.codec import encode_result
from hse_doc_studio.core.jobs.entities import JobResult
from hse_doc_studio.core.jobs.enums import JobErrorCategory, JobStatus, RunnerErrorCode
from hse_doc_studio.core.jobs.errors import JobError, JobFailure
from hse_doc_studio.core.jobs.files import ArtifactRef
from hse_doc_studio.core.jobs.wire import (
    DEFAULT_HEARTBEAT_S,
    DEFAULT_LEASE_S,
    MAX_POLL_WAIT_S,
    RUNNER_PROTOCOL_VERSION,
    ArtifactUploadRequest,
    CompleteRequest,
    HeartbeatRequest,
    JobEnvelope,
    LogBatch,
    PollRequest,
    RunnerRegisterRequest,
    RunnerRegisterResponse,
)
from hse_doc_studio.infra.runner.backoff import Backoff
from hse_doc_studio.infra.runner.client import RunnerApiError, RunnerClient, RunnerUnreachable
from hse_doc_studio.infra.runner.executor import JobContext, JobExecutor, JobOutcome, OutputFile
from hse_doc_studio.infra.runner.log_batcher import DEFAULT_FLUSH_S, LogBatcher

logger = logging.getLogger(__name__)

_FATAL_CODES = frozenset({RunnerErrorCode.runner_unauthorized.value, RunnerErrorCode.runner_disabled.value})
_LEASE_LOST_CODES = frozenset(
    {
        RunnerErrorCode.stale_attempt.value,
        RunnerErrorCode.job_not_found.value,
        RunnerErrorCode.job_not_running.value,
        RunnerErrorCode.job_token_invalid.value,
    }
)
# Запас на остановку исполнителя после принудительной отмены при выключении.
_FORCE_GRACE_S = 5.0


class RunnerFatalError(Exception):
    """Раннеру нельзя продолжать: токен отвергнут, раннер отключён или версия протокола несовместима."""


@dataclass(frozen=True)
class RunnerLoopConfig:
    name: str
    version: str
    tags: frozenset[str] = frozenset()
    concurrency: int = 1
    resource_class: str = "standard"
    poll_wait_s: int = MAX_POLL_WAIT_S
    log_flush_s: float = DEFAULT_FLUSH_S
    drain_timeout_s: float = 30.0
    # Пульс и аренда по умолчанию берутся из ответа регистрации; переопределение нужно тестам.
    heartbeat_s: float | None = None
    backoff_factory: Callable[[], Backoff] = field(default=lambda: Backoff(base_s=0.5, cap_s=30.0))


class RunnerLoop:
    """Цикл раннера: регистрация, долгий опрос при свободных слотах, по задаче свой пульс и порции лога.

    Исполнение вида задачи подключается через `JobExecutor`, цикл Docker не знает. Сетевые сбои
    переживаются паузами с нарастанием и повторной регистрацией; устаревшая попытка (аренда
    потеряна) бросается без отчёта: сервер вернёт задачу в очередь.
    """

    def __init__(self, client: RunnerClient, executor: JobExecutor, config: RunnerLoopConfig) -> None:
        if config.concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        self._client = client
        self._executor = executor
        self._config = config
        self._stop = asyncio.Event()
        self._force = asyncio.Event()
        self._slot_freed = asyncio.Event()
        self._jobs: set[asyncio.Task[None]] = set()
        self._registration: RunnerRegisterResponse | None = None

    @property
    def running_jobs(self) -> int:
        return len(self._jobs)

    def request_stop(self) -> None:
        """Прекращает опрос; идущие задачи доделываются в пределах `drain_timeout_s`."""
        self._stop.set()

    async def run(self) -> None:
        if not self._client.is_registered:
            await self._register_until_ready()
        backoff = self._config.backoff_factory()
        while not self._stop.is_set():
            if len(self._jobs) >= self._config.concurrency:
                self._slot_freed.clear()
                await self._wait_stop_or(self._slot_freed)
                continue
            try:
                response = await self._poll()
            except (RunnerApiError, RunnerUnreachable) as exc:
                self._raise_if_fatal(exc)
                logger.warning("poll failed: %s", exc)
                await self._sleep_or_stop(backoff.next())
            else:
                backoff.reset()
                if response is not None:
                    self._spawn(response)
        await self._drain()

    async def _register(self) -> RunnerRegisterResponse:
        cfg = self._config
        request = RunnerRegisterRequest(
            name=cfg.name,
            protocol=RUNNER_PROTOCOL_VERSION,
            version=cfg.version,
            tags=cfg.tags,
            concurrency=cfg.concurrency,
            resource_class=cfg.resource_class,
        )
        self._registration = await self._client.register(request)
        return self._registration

    async def _register_until_ready(self) -> None:
        backoff = self._config.backoff_factory()
        while not self._stop.is_set():
            try:
                await self._register()
            except RunnerApiError as exc:
                raise RunnerFatalError(f"registration refused: {exc}") from exc
            except RunnerUnreachable as exc:
                logger.warning("registration: api unreachable (%s)", exc)
                await self._sleep_or_stop(backoff.next())
            else:
                return

    async def _poll(self) -> JobEnvelope | None:
        free = self._config.concurrency - len(self._jobs)
        request = PollRequest(wait_s=self._config.poll_wait_s, free_slots=free)
        poll = asyncio.create_task(self._client.poll(request))
        stop = asyncio.create_task(self._stop.wait())
        try:
            await asyncio.wait({poll, stop}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            stop.cancel()
            if not poll.done():
                # Запрос оборван при выключении; взятую сервером задачу вернёт reaper по аренде.
                poll.cancel()
        if not poll.done() or poll.cancelled():
            with contextlib.suppress(asyncio.CancelledError):
                await poll
            return None
        return poll.result().envelope

    def _raise_if_fatal(self, exc: Exception) -> None:
        if isinstance(exc, RunnerApiError) and exc.code in _FATAL_CODES:
            raise RunnerFatalError(str(exc)) from exc

    async def _wait_stop_or(self, event: asyncio.Event) -> None:
        waiter = asyncio.create_task(event.wait())
        stop = asyncio.create_task(self._stop.wait())
        try:
            await asyncio.wait({waiter, stop}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            waiter.cancel()
            stop.cancel()

    async def _sleep_or_stop(self, delay_s: float) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._stop.wait(), delay_s)

    def _spawn(self, envelope: JobEnvelope) -> None:
        task = asyncio.create_task(self._run_job(envelope))
        self._jobs.add(task)
        task.add_done_callback(self._on_job_done)

    def _on_job_done(self, task: asyncio.Task[None]) -> None:
        self._jobs.discard(task)
        self._slot_freed.set()
        if not task.cancelled() and (exc := task.exception()) is not None:
            logger.error("runner job task crashed", exc_info=exc)

    async def _drain(self) -> None:
        if not self._jobs:
            return
        _, pending = await asyncio.wait(set(self._jobs), timeout=self._config.drain_timeout_s)
        if not pending:
            return
        logger.warning("drain timeout: cancelling %d running job(s)", len(pending))
        self._force.set()
        _, pending = await asyncio.wait(pending, timeout=_FORCE_GRACE_S)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.wait(pending)

    async def _run_job(self, envelope: JobEnvelope) -> None:
        job_id = str(envelope.spec.id)
        token = envelope.job_token
        attempt = envelope.attempt
        client = self._client
        cancelled = asyncio.Event()

        async def send_log(batch: LogBatch) -> None:
            await client.send_log(job_id, token, batch)

        batcher = LogBatcher(send_log, attempt, flush_s=self._config.log_flush_s)
        batcher.start()
        execution = asyncio.create_task(
            self._executor.execute(envelope, JobContext(log=batcher.append, cancelled=cancelled))
        )
        heartbeat = asyncio.create_task(self._heartbeats(envelope))
        forced = asyncio.create_task(self._force.wait())
        try:
            outcome = await self._await_outcome(envelope, execution, heartbeat, forced, cancelled)
        finally:
            heartbeat.cancel()
            forced.cancel()
            await asyncio.gather(heartbeat, forced, return_exceptions=True)
            await batcher.close()
        if outcome is None:
            logger.warning("job %s: lease lost, no report", job_id)
            return
        await self._report(envelope, outcome)

    async def _await_outcome(
        self,
        envelope: JobEnvelope,
        execution: asyncio.Task[JobOutcome],
        heartbeat: asyncio.Task[str],
        forced: asyncio.Task[bool],
        cancelled: asyncio.Event,
    ) -> JobOutcome | None:
        """Итог попытки; `None` когда аренда потеряна и отчитываться нечем."""
        waiting = {execution, heartbeat, forced}
        await asyncio.wait(waiting, timeout=envelope.timeout_s, return_when=asyncio.FIRST_COMPLETED)
        if execution.done():
            return _outcome_of(execution)
        if heartbeat.done() and heartbeat.result() == "lost":
            await self._stop_execution(execution, cancelled, JobStatus.cancelled, "lease_lost")
            return None
        if heartbeat.done():
            return await self._stop_execution(execution, cancelled, JobStatus.cancelled, "cancelled")
        if forced.done():
            return await self._stop_execution(execution, cancelled, JobStatus.cancelled, "runner_shutdown")
        return await self._stop_execution(execution, cancelled, JobStatus.timed_out, "job_timeout")

    async def _stop_execution(
        self, execution: asyncio.Task[JobOutcome], cancelled: asyncio.Event, status: JobStatus, code: str
    ) -> JobOutcome:
        cancelled.set()
        if not execution.done():
            execution.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await execution
        return JobOutcome(
            JobResult(status=status, error=JobError(category=JobErrorCategory.internal, code=code, detail=code))
        )

    def _heartbeat_timing(self) -> tuple[float, float]:
        registration = self._registration
        lease_s = registration.lease_s if registration else DEFAULT_LEASE_S
        interval = self._config.heartbeat_s or (registration.heartbeat_s if registration else DEFAULT_HEARTBEAT_S)
        return interval, lease_s

    async def _heartbeats(self, envelope: JobEnvelope) -> str:
        """Возвращает `cancel` по флагу отмены или `lost`, когда аренду не удержать."""
        interval, lease_s = self._heartbeat_timing()
        last_ok = time.monotonic()
        while True:
            await asyncio.sleep(interval)
            verdict = await self._beat(envelope)
            if verdict == "ok":
                last_ok = time.monotonic()
            elif verdict == "unreachable" and time.monotonic() - last_ok >= lease_s:
                return "lost"
            elif verdict in ("lost", "cancel"):
                return verdict

    async def _beat(self, envelope: JobEnvelope) -> str:
        try:
            reply = await self._client.heartbeat(
                str(envelope.spec.id), envelope.job_token, HeartbeatRequest(envelope.attempt)
            )
        except RunnerApiError as exc:
            if _lease_is_gone(exc):
                return "lost"
            logger.warning("heartbeat rejected: %s", exc)
            return "rejected"
        except RunnerUnreachable:
            return "unreachable"
        return "cancel" if reply.cancel else "ok"

    async def _report(self, envelope: JobEnvelope, outcome: JobOutcome) -> None:
        job_id = str(envelope.spec.id)
        token = envelope.job_token
        result = outcome.result
        refs: tuple[ArtifactRef, ...] = ()
        if result.status is JobStatus.succeeded and outcome.outputs:
            try:
                await self._upload(envelope, outcome.outputs)
            except (RunnerApiError, RunnerUnreachable, OSError) as exc:
                if isinstance(exc, RunnerApiError) and _lease_is_gone(exc):
                    logger.warning("job %s: attempt is stale, outputs dropped", job_id)
                    return
                logger.exception("job %s: artifact upload failed", job_id)
                result = JobResult(
                    status=JobStatus.failed,
                    error=JobError(JobErrorCategory.unavailable, "artifact_upload_failed", str(exc)),
                )
            else:
                refs = tuple(out.ref for out in outcome.outputs)
        request = CompleteRequest(attempt=envelope.attempt, result=encode_result(result), artifacts=refs)
        try:
            await self._client.complete(job_id, token, request)
        except RunnerApiError as exc:
            logger.warning("job %s: completion not accepted: %s", job_id, exc)
        except RunnerUnreachable:
            logger.exception("job %s: completion not delivered, lease will expire", job_id)

    async def _upload(self, envelope: JobEnvelope, outputs: tuple[OutputFile, ...]) -> None:
        job_id = str(envelope.spec.id)
        token = envelope.job_token
        for out in outputs:
            data = await asyncio.to_thread(out.path.read_bytes)
            slot = await self._client.announce_artifact(job_id, token, ArtifactUploadRequest(envelope.attempt, out.ref))
            if slot.url is None:
                await self._client.put_artifact(job_id, token, out.ref.sha256, data)
            else:
                await self._client.put_to_url(slot.url, data)


def _lease_is_gone(exc: RunnerApiError) -> bool:
    return exc.status in (401, 403, 404, 409) or exc.code in _LEASE_LOST_CODES


def _outcome_of(execution: asyncio.Task[JobOutcome]) -> JobOutcome:
    if execution.cancelled():
        return JobOutcome(
            JobResult(status=JobStatus.cancelled, error=JobError(JobErrorCategory.internal, "cancelled", "cancelled"))
        )
    exc = execution.exception()
    if exc is None:
        return execution.result()
    if isinstance(exc, JobFailure):
        return JobOutcome(JobResult(status=JobStatus.failed, error=exc.error))
    logger.error("executor crashed", exc_info=exc)
    return JobOutcome(
        JobResult(
            status=JobStatus.failed,
            error=JobError(JobErrorCategory.internal, "executor_crashed", f"{type(exc).__name__}: {exc}"),
        )
    )
