from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from hse_doc_studio.core.jobs.codec import encode_result
from hse_doc_studio.core.jobs.entities import JobResult
from hse_doc_studio.core.jobs.enums import JobErrorCategory, JobKind, JobStatus, RunnerErrorCode
from hse_doc_studio.core.jobs.errors import JobError, JobFailure
from hse_doc_studio.core.jobs.files import ArtifactRef
from hse_doc_studio.core.jobs.relay import RELAY_KEEPALIVE_S, RELAY_TAG
from hse_doc_studio.core.jobs.runners import DeclaredAiEndpoint, RunnerHostKind
from hse_doc_studio.core.jobs.wire import (
    DEFAULT_HEARTBEAT_S,
    DEFAULT_LEASE_S,
    FEATURE_AI_RELAY,
    FEATURE_AI_SLOTS,
    FEATURE_ANNOUNCE,
    FEATURE_OFFLINE,
    MAX_POLL_WAIT_S,
    RUNNER_PROTOCOL_VERSION,
    ArtifactUploadRequest,
    CompleteRequest,
    HeartbeatRequest,
    JobEnvelope,
    LogBatch,
    PollRequest,
    RunnerAnnounceRequest,
    RunnerAnnounceResponse,
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

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class RunnerLoopState(StrEnum):
    registering = "registering"
    online = "online"
    paused = "paused"
    unreachable = "unreachable"
    stopped = "stopped"


class IRunnerLoopObserver(Protocol):
    """Наблюдатель цикла (локальная Студия показывает по нему состояние раннера)."""

    def on_state(self, state: RunnerLoopState, code: str | None = None) -> None: ...
    def on_job_started(self, job_id: str, kind: str) -> None: ...
    def on_job_finished(self, job_id: str, kind: str, status: str) -> None: ...


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
    # Слоты ретрансляции ИИ отдельно от сборок: длинная сборка не блокирует чат и наоборот.
    ai_concurrency: int = 0
    host_kind: RunnerHostKind = RunnerHostKind.cli
    ai_endpoints: tuple[DeclaredAiEndpoint, ...] = ()
    # False: не брать сборки сейчас (ретрансляцию брать можно).
    gate: Callable[[], bool] | None = None
    # Пауза перед новой проверкой, пока шлюз закрыт и брать нечего.
    gate_recheck_s: float = 1.0


class RunnerLoop:
    """Цикл раннера: регистрация, долгий опрос при свободных слотах, по задаче свой пульс и порции лога.

    Исполнение вида задачи подключается через `JobExecutor`, цикл Docker не знает. Сетевые сбои
    переживаются паузами с нарастанием и повторной регистрацией; устаревшая попытка (аренда
    потеряна) бросается без отчёта: сервер вернёт задачу в очередь.
    """

    def __init__(
        self,
        client: RunnerClient,
        executor: JobExecutor,
        config: RunnerLoopConfig,
        *,
        observer: IRunnerLoopObserver | None = None,
    ) -> None:
        if config.concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        self._client = client
        self._executor = executor
        self._config = config
        self._observer = observer
        self._stop = asyncio.Event()
        self._force = asyncio.Event()
        self._slot_freed = asyncio.Event()
        # Освободился слот сборки или ИИ: долгий опрос, открытый без свободного слота этого вида, устарел.
        self._job_slot_freed = asyncio.Event()
        self._ai_slot_freed = asyncio.Event()
        self._jobs: set[asyncio.Task[None]] = set()
        self._ai_jobs: set[asyncio.Task[None]] = set()
        self._registration: RunnerRegisterResponse | None = None
        self._announced: RunnerAnnounceResponse | None = None
        self._ai_endpoints = config.ai_endpoints
        self._state: RunnerLoopState | None = None

    @property
    def running_jobs(self) -> int:
        return len(self._jobs) + len(self._ai_jobs)

    @property
    def runner_id(self) -> str | None:
        if self._announced is not None:
            return self._announced.runner_id
        return self._registration.runner_id if self._registration is not None else None

    @property
    def features(self) -> frozenset[str]:
        return self._client.features

    def _set_state(self, state: RunnerLoopState, code: str | None = None) -> None:
        if state is self._state and code is None:
            return
        self._state = state
        if self._observer is not None:
            self._observer.on_state(state, code)

    async def reannounce(self, *, ai_endpoints: tuple[DeclaredAiEndpoint, ...] | None = None) -> None:
        """Сообщить серверу новое описание (адреса ИИ поменялись) без перезапуска цикла."""
        if ai_endpoints is not None:
            self._ai_endpoints = ai_endpoints
        await self._announce()

    def _announce_request(self) -> RunnerAnnounceRequest:
        cfg = self._config
        endpoints = self._ai_endpoints
        relay = cfg.ai_concurrency > 0 and bool(endpoints)
        features = {FEATURE_ANNOUNCE, FEATURE_OFFLINE} | ({FEATURE_AI_SLOTS, FEATURE_AI_RELAY} if relay else set())
        tags = set(cfg.tags) | ({RELAY_TAG} if relay else set())
        return RunnerAnnounceRequest(
            name=cfg.name,
            version=cfg.version,
            tags=frozenset(tags),
            concurrency=cfg.concurrency,
            ai_concurrency=cfg.ai_concurrency if relay else 0,
            host_kind=cfg.host_kind,
            features=frozenset(features),
            ai_endpoints=endpoints if relay else (),
        )

    async def _announce(self) -> None:
        """Согласование возможностей; старый сервер (404) оставляет раннер в прежнем режиме."""
        try:
            self._announced = await self._client.announce(self._announce_request())
        except RunnerApiError as exc:
            self._raise_if_fatal(exc)
            logger.warning("announce rejected, staying on protocol 1.0: %s", exc)
            self._announced = None
            return
        if self._announced is None:
            logger.info("server does not know /announce: protocol 1.0 without ai relay")
        else:
            self._set_state(RunnerLoopState.paused if self._announced.paused else RunnerLoopState.online)

    async def _announce_until_ready(self) -> None:
        backoff = self._config.backoff_factory()
        while not self._stop.is_set():
            try:
                await self._announce()
            except RunnerUnreachable as exc:
                self._set_state(RunnerLoopState.unreachable)
                logger.warning("announce: api unreachable (%s)", exc)
                await self._sleep_or_stop(backoff.next())
            else:
                return

    def request_stop(self) -> None:
        """Прекращает опрос; идущие задачи доделываются в пределах `drain_timeout_s`."""
        self._stop.set()

    async def run(self) -> None:
        self._set_state(RunnerLoopState.registering)
        try:
            if not self._client.is_registered:
                await self._register_until_ready()
            await self._announce_until_ready()
            await self._poll_loop()
            await self._drain()
            await self._say_offline()
        finally:
            self._set_state(RunnerLoopState.stopped)

    def _free_slots(self) -> tuple[int, int]:
        """Свободные слоты сборок (с учётом шлюза) и ретрансляции (только после согласования `ai_slots`)."""
        gate = self._config.gate
        jobs = self._config.concurrency - len(self._jobs) if gate is None or gate() else 0
        ai = 0
        if FEATURE_AI_SLOTS in self._client.features:
            ai = self._config.ai_concurrency - len(self._ai_jobs)
        return max(jobs, 0), max(ai, 0)

    async def _poll_loop(self) -> None:
        backoff = self._config.backoff_factory()
        while not self._stop.is_set():
            free_jobs, free_ai = self._free_slots()
            if free_jobs + free_ai < 1:
                await self._wait_for_slot()
                continue
            try:
                response = await self._poll(free_jobs, free_ai)
            except (RunnerApiError, RunnerUnreachable) as exc:
                self._on_poll_failed(exc)
                await self._sleep_or_stop(backoff.next())
                continue
            backoff.reset()
            if self._state in (RunnerLoopState.registering, RunnerLoopState.unreachable, None):
                self._set_state(RunnerLoopState.online)
            if response is not None:
                self._spawn(response)

    async def _wait_for_slot(self) -> None:
        """Слот освободится по окончании задачи; шлюз закрыт без задач: проверим снова чуть позже."""
        if self.running_jobs == 0:
            await self._sleep_or_stop(self._config.gate_recheck_s)
            return
        self._slot_freed.clear()
        await self._wait_stop_or_timeout(self._slot_freed, self._config.gate_recheck_s)

    def _on_poll_failed(self, exc: RunnerApiError | RunnerUnreachable) -> None:
        self._raise_if_fatal(exc)
        if isinstance(exc, RunnerUnreachable):
            self._set_state(RunnerLoopState.unreachable)
        logger.warning("poll failed: %s", exc)

    async def _say_offline(self) -> None:
        """Мягкая остановка: сервер сразу уводит сборки хозяина на общие, не дожидаясь окна."""
        if FEATURE_OFFLINE not in self._client.features:
            return
        try:
            await self._client.offline()
        except (RunnerApiError, RunnerUnreachable) as exc:
            logger.warning("offline notice not delivered: %s", exc)

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
                raise RunnerFatalError(f"registration refused: {exc}", exc.code) from exc
            except RunnerUnreachable as exc:
                logger.warning("registration: api unreachable (%s)", exc)
                await self._sleep_or_stop(backoff.next())
            else:
                return

    async def _poll(self, free_jobs: int, free_ai: int) -> JobEnvelope | None:
        """Долгий опрос со снимком свободных слотов; обрывается остановкой и устареванием снимка.

        Опрос, открытый без свободного слота сборки (единственная сборка ещё шла, опрашиваем ради ИИ),
        до конца wait_s не взял бы следующую сборку хозяина, и она ушла бы на общие по окну ожидания.
        Поэтому освобождение слота того вида, которого в снимке не было, обрывает опрос: цикл тут же
        опрашивает снова со свежими слотами. Сервер замечает отключение и задачу в оборванный опрос не выдаёт.
        """
        request = PollRequest(wait_s=self._config.poll_wait_s, free_slots=free_jobs, free_ai_slots=free_ai)
        # Снимок слотов только что взят, ожиданий между ним и сбросом нет: освобождение не потеряется.
        stale: set[asyncio.Task[bool]] = set()
        if free_jobs == 0:
            self._job_slot_freed.clear()
            stale.add(asyncio.create_task(self._job_slot_freed.wait()))
        if free_ai == 0 and FEATURE_AI_SLOTS in self._client.features:
            self._ai_slot_freed.clear()
            stale.add(asyncio.create_task(self._ai_slot_freed.wait()))
        poll = asyncio.create_task(self._client.poll(request))
        stop = asyncio.create_task(self._stop.wait())
        try:
            await asyncio.wait({poll, stop, *stale}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            stop.cancel()
            for waiter in stale:
                waiter.cancel()
            if not poll.done():
                # Запрос оборван при выключении или устаревшем снимке; взятую сервером задачу вернёт reaper по аренде.
                poll.cancel()
        if not poll.done() or poll.cancelled():
            with contextlib.suppress(asyncio.CancelledError):
                await poll
            return None
        return poll.result().envelope

    def _raise_if_fatal(self, exc: Exception) -> None:
        if isinstance(exc, RunnerApiError) and exc.code in _FATAL_CODES:
            raise RunnerFatalError(str(exc), exc.code) from exc

    async def _wait_stop_or(self, event: asyncio.Event) -> None:
        waiter = asyncio.create_task(event.wait())
        stop = asyncio.create_task(self._stop.wait())
        try:
            await asyncio.wait({waiter, stop}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            waiter.cancel()
            stop.cancel()

    async def _wait_stop_or_timeout(self, event: asyncio.Event, timeout_s: float) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._wait_stop_or(event), timeout_s)

    async def _sleep_or_stop(self, delay_s: float) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._stop.wait(), delay_s)

    def _spawn(self, envelope: JobEnvelope) -> None:
        task = asyncio.create_task(self._run_job(envelope))
        (self._ai_jobs if envelope.spec.kind is JobKind.ai_relay else self._jobs).add(task)
        task.add_done_callback(self._on_job_done)

    def _on_job_done(self, task: asyncio.Task[None]) -> None:
        (self._ai_slot_freed if task in self._ai_jobs else self._job_slot_freed).set()
        self._jobs.discard(task)
        self._ai_jobs.discard(task)
        self._slot_freed.set()
        if not task.cancelled() and (exc := task.exception()) is not None:
            logger.error("runner job task crashed", exc_info=exc)

    async def _drain(self) -> None:
        if not self.running_jobs:
            return
        _, pending = await asyncio.wait(self._jobs | self._ai_jobs, timeout=self._config.drain_timeout_s)
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
        if self._observer is not None:
            self._observer.on_job_started(job_id, envelope.spec.kind.value)
        try:
            outcome = await self._await_outcome(envelope, execution, heartbeat, forced, cancelled)
        finally:
            heartbeat.cancel()
            forced.cancel()
            await asyncio.gather(heartbeat, forced, return_exceptions=True)
            await batcher.close()
        if self._observer is not None:
            status = "lost" if outcome is None else outcome.result.status.value
            self._observer.on_job_finished(job_id, envelope.spec.kind.value, status)
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

    def _heartbeat_timing(self, kind: JobKind) -> tuple[float, float]:
        registration = self._registration
        lease_s = registration.lease_s if registration else DEFAULT_LEASE_S
        interval = self._config.heartbeat_s or (registration.heartbeat_s if registration else DEFAULT_HEARTBEAT_S)
        if kind is JobKind.ai_relay:
            # Пока порций нет, отмена ретрансляции доходит только пульсом: он чаще обычного.
            keepalive = self._announced.relay_keepalive_s if self._announced else RELAY_KEEPALIVE_S
            interval = min(interval, float(keepalive))
        return interval, lease_s

    async def _heartbeats(self, envelope: JobEnvelope) -> str:
        """Возвращает `cancel` по флагу отмены или `lost`, когда аренду не удержать."""
        interval, lease_s = self._heartbeat_timing(envelope.spec.kind)
        last_ok = time.monotonic()
        while True:
            await asyncio.sleep(interval)
            verdict = await self._beat(envelope)
            if verdict == "ok":
                last_ok = time.monotonic()
            elif verdict in ("unreachable", "rejected") and time.monotonic() - last_ok >= lease_s:
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
