"""Диспетчер задач серверного режима: ставит задачу в очередь Postgres и ждёт итог.

Тот же порт `IJobDispatcher`, что у `LocalJobDispatcher`, но работа идёт на удалённом раннере.
Запись сборки пишет вызывающий до `submit`; манифест входа собирается и грузится в хранилище уже
после неё, в рабочем потоке, и только потом задача попадает в очередь. Сбой на этом шаге даёт
итоговую запись `failed` с типизированным кодом, а не вечное `pending`. Итог задачи приходит
опросом очереди: выдача раннеру это `on_started`, завершение это `on_finished`, оба по одному разу.

Выходы удачной задачи кладутся на том до хуков, а затем итог получает метку применённого. Упавший между
этими шагами api довершает работу в `recover()` при старте: хуки пересобираются фабрикой по спецификации
из записи очереди, актор берётся из снимка в конверте.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import stat
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog

from hse_doc_studio.core.access.context import ActorRequired, set_current_actor
from hse_doc_studio.core.access.entities import Actor, ActorKind, ActorSource, Role
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.core.jobs.applier import (
    ApplyError,
    IJobApplyLedger,
    IJobHooksFactory,
    IJobResultApplier,
)
from hse_doc_studio.core.jobs.codec import decode, decode_envelope, decode_result, encode_envelope
from hse_doc_studio.core.jobs.entities import CompileResult, JobResult, JobSpec, compile_payload_of
from hse_doc_studio.core.jobs.enums import JobErrorCategory, JobKind, JobState, JobStatus, RunnerErrorCode
from hse_doc_studio.core.jobs.errors import JobError, NoRunnerAvailableError, QueuedJobNotFoundError
from hse_doc_studio.core.jobs.files import ArtifactRef
from hse_doc_studio.core.jobs.office import OfficeConvertPayload
from hse_doc_studio.core.jobs.pack import PackSubmissionPayload
from hse_doc_studio.core.jobs.protocols import IJobHooks, IJobObserver
from hse_doc_studio.core.jobs.queue import EnqueueRequest, IJobQueue, QueuedJob
from hse_doc_studio.core.jobs.registry import job_kind_spec
from hse_doc_studio.core.jobs.runners import IRunnerRepository, Runner
from hse_doc_studio.core.jobs.verify import VerifyDetachedPayload
from hse_doc_studio.core.jobs.wire import JobEnvelope
from hse_doc_studio.core.projects.volume import IProjectVolume
from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.core.storage.manifest import IBlobUploader, ManifestError, ManifestLimits

logger = structlog.get_logger()

ERROR_CODE_STAGING_FAILED = "staging_failed"
ERROR_CODE_JOB_LOST = "job_lost"
ERROR_CODE_TIMED_OUT = "timed_out"
ERROR_CODE_CANCELLED = "cancelled"

DEFAULT_POLL_INTERVAL_S = 0.5
# Раннер живой, если опрашивал сервер не дольше этого назад: предел долгого опроса плюс запас.
DEFAULT_RUNNER_LIVE_WINDOW_S = 60.0
DEFAULT_TIMEOUT_S = 600.0

# Папки, которые в манифест сборки не попадают: служебные, выходы и чужая история.
EXCLUDED_DIRS = frozenset({".git", ".hse-studio", ".build", "submissions", "node_modules", "__pycache__"})

RoleSource = Callable[[Actor, UUID], Awaitable[Role | None]]


@dataclass(frozen=True)
class RecoveryReport:
    """Что сделал `recover()`: довершено завершённых, подхвачено идущих, не вышло."""

    finished: int = 0
    adopted: int = 0
    failed: int = 0


def _utc_now() -> datetime:
    return datetime.now(UTC)


class QueueJobDispatcher:
    """Задачи идут через очередь; идущие в этом процессе отслеживаются для `is_active` и отмены."""

    def __init__(  # noqa: PLR0913
        self,
        queue: IJobQueue,
        uploader: IBlobUploader,
        runners: IRunnerRepository,
        *,
        limits: ManifestLimits | None = None,
        role_source: RoleSource | None = None,
        applier: IJobResultApplier | None = None,
        ledger: IJobApplyLedger | None = None,
        hooks_factory: IJobHooksFactory | None = None,
        volume: IProjectVolume | None = None,
        settings_repo: ISettingsRepository | None = None,
        poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
        runner_live_window_s: float = DEFAULT_RUNNER_LIVE_WINDOW_S,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._queue = queue
        self._uploader = uploader
        self._runners = runners
        self._limits = limits
        self._role_source = role_source
        self._applier = applier
        self._ledger = ledger
        self._hooks_factory = hooks_factory
        self._volume = volume
        self._settings_repo = settings_repo
        self._interval = poll_interval_s
        self._live_window = timedelta(seconds=runner_live_window_s)
        self._clock = clock
        # Идущие в этом процессе задачи всех видов от постановки до итога.
        self._in_flight: dict[UUID, JobSpec] = {}
        self._cancelled: set[UUID] = set()
        self._tasks: set[asyncio.Task[None]] = set()
        self._detached: set[asyncio.Task[None]] = set()

    # --- preflight ---

    async def preflight(self, spec: JobSpec) -> None:
        """Нужен живой раннер с нужными тегами; иначе `NoRunnerAvailableError`."""
        now = self._clock()
        for runner in await self._runners.list():
            if self._serves(runner, spec.tags, now):
                return
        raise NoRunnerAvailableError(spec.tags)

    def _serves(self, runner: Runner, tags: frozenset[str], now: datetime) -> bool:
        if runner.revoked_at is not None or runner.paused or runner.last_seen_at is None:
            return False
        return now - runner.last_seen_at <= self._live_window and tags <= runner.tags

    # --- compile ---

    def submit(self, spec: JobSpec, hooks: IJobHooks) -> None:
        compile_payload_of(spec)
        self._in_flight[spec.id] = spec
        task = asyncio.create_task(self._drive_compile(spec, hooks))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _drive_compile(self, spec: JobSpec, hooks: IJobHooks) -> None:
        set_interface_language(spec.locale.value)
        try:
            await self._run_compile(spec, hooks)
        except Exception:
            logger.exception("queued compile failed", compile_id=str(spec.id))
        finally:
            self._in_flight.pop(spec.id, None)
            self._cancelled.discard(spec.id)

    async def _run_compile(self, spec: JobSpec, hooks: IJobHooks) -> None:
        try:
            queued = await self._stage_and_enqueue(spec, None)
        except Exception as exc:
            logger.warning("compile staging failed", compile_id=str(spec.id), exc=repr(exc))
            await hooks.on_finished(spec, _staging_failure(spec, exc), f"[error] {exc}")
            return
        if queued is None:
            await hooks.on_finished(spec, _unfinished(spec, JobStatus.cancelled, None), "[cancelled]")
            return
        await self._follow_compile(spec, hooks)

    async def _follow_compile(self, spec: JobSpec, hooks: IJobHooks) -> None:
        """Ждёт задачу в очереди и закрывает её: выходы на том, хуки, метка применённого."""
        rejected = False

        async def claimed() -> bool:
            nonlocal rejected
            accepted = await hooks.on_started(spec)
            rejected = not accepted
            return accepted

        job = await self._wait(spec.id, claimed)
        if rejected:
            # Записи сборки нет: задача прекращается, как и во встроенном диспетчере.
            await self._cancel_quietly(spec.id)
            return
        await self._finish(spec, job, hooks)

    async def _finish(self, spec: JobSpec, job: QueuedJob | None, hooks: IJobHooks | None) -> None:
        result = await self._applied_result(spec, job)
        if hooks is not None:
            await hooks.on_finished(spec, result, "")
        await self._settle(spec, job)

    async def cancel(self, job_id: UUID) -> bool:
        tracked = job_id in self._in_flight
        if tracked:
            self._cancelled.add(job_id)
        job = await self._queue.get(job_id)
        if job is None or job.state.is_terminal:
            return tracked
        await self._queue.request_cancel(job_id)
        return True

    # --- run / detached ---

    async def run(self, spec: JobSpec, *, timeout_s: float | None = None) -> JobResult:
        if not job_kind_spec(spec.kind).policy.awaitable:
            raise ValueError(f"job kind {spec.kind} cannot be awaited")
        return await self._execute(spec, timeout_s)

    def submit_detached(self, spec: JobSpec, observer: IJobObserver | None = None) -> None:
        if not job_kind_spec(spec.kind).policy.detachable:
            raise ValueError(f"job kind {spec.kind} cannot run detached")
        loop = asyncio.get_running_loop()
        self._in_flight[spec.id] = spec
        task = loop.create_task(self._run_detached(spec, observer))
        self._detached.add(task)
        task.add_done_callback(self._detached.discard)

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
        set_interface_language(spec.locale.value)
        self._in_flight[spec.id] = spec
        try:
            try:
                queued = await self._stage_and_enqueue(spec, timeout_s)
            except (ManifestError, OSError) as exc:
                return _staging_failure(spec, exc)
            if queued is None:
                return _unfinished(spec, JobStatus.cancelled, None)
            try:
                async with asyncio.timeout(timeout_s):
                    job = await self._wait(spec.id, None)
            except TimeoutError:
                await self._cancel_quietly(spec.id)
                error = JobError(JobErrorCategory.internal, ERROR_CODE_TIMED_OUT, f"timed out after {timeout_s} s")
                return JobResult(status=JobStatus.timed_out, error=error)
            except asyncio.CancelledError:
                await asyncio.shield(self._cancel_quietly(spec.id))
                raise
            result = await self._applied_result(spec, job)
            await self._settle(spec, job)
            return result
        finally:
            self._in_flight.pop(spec.id, None)
            self._cancelled.discard(spec.id)

    async def _cancel_quietly(self, job_id: UUID) -> None:
        with contextlib.suppress(QueuedJobNotFoundError):
            await self._queue.request_cancel(job_id)

    # --- применение результата ---

    async def _applied_result(self, spec: JobSpec, job: QueuedJob | None) -> JobResult:
        """Итог задачи; выходы удачной задачи к этому моменту уже лежат на томе."""
        result = self._result_of(spec, job)
        if self._applier is None or job is None or result.status is not JobStatus.succeeded:
            return result
        artifacts = _artifacts_of(job)
        try:
            await self._applier.apply(spec, artifacts)
        except ApplyError as exc:
            logger.warning("job outputs not applied", job_id=str(spec.id), code=exc.code, detail=exc.detail)
            return _apply_failure(spec, exc)
        return result

    async def _settle(self, spec: JobSpec, job: QueuedJob | None) -> None:
        """Метка применённого, затем уборка принятых выходов: до метки они нужны для повторного применения."""
        if job is None:
            return
        if self._ledger is not None and not await self._ledger.mark_applied(job.id):
            logger.info("job result was already applied", job_id=str(job.id))
        if self._applier is not None and job.result is not None and job.result.get("artifacts"):
            await self._applier.discard(spec)

    # --- восстановление после рестарта ---

    async def recover(self) -> RecoveryReport:
        """Довершает завершённые задачи без метки применённого и подхватывает идущие compile.

        Вызывается один раз при старте api до приёма запросов: хуки в памяти прошлого процесса потеряны.
        """
        if self._ledger is None or self._volume is None:
            return RecoveryReport()
        finished = failed = 0
        for job in await self._ledger.list_unapplied():
            if job.id in self._in_flight:
                continue
            try:
                await asyncio.create_task(self._recover_finished(job))
                finished += 1
            except Exception:
                logger.exception("job recovery failed", job_id=str(job.id))
                failed += 1
        adopted, not_adopted = await self._adopt_running()
        return RecoveryReport(finished=finished, adopted=adopted, failed=failed + not_adopted)

    async def _adopt_running(self) -> tuple[int, int]:
        adopted = failed = 0
        for state in (JobState.queued, JobState.running):
            for job in await self._queue.list(state=state):
                if job.id in self._in_flight or job.kind is not JobKind.compile:
                    continue
                try:
                    adopted += self._adopt(job)
                except Exception:
                    logger.exception("job adoption failed", job_id=str(job.id))
                    failed += 1
        return adopted, failed

    def _recovered_spec(self, job: QueuedJob) -> JobSpec:
        assert self._volume is not None  # noqa: S101
        envelope = decode_envelope({**job.payload, "job_token": "-", "attempt": max(job.attempt, 1)})
        spec = envelope.spec
        actor = replace(spec.actor, source=ActorSource.job)
        return replace(spec, actor=actor, local_root=self._volume.path_of(job.project_id))

    def _enter_job_context(self, spec: JobSpec) -> None:
        set_current_actor(spec.actor)
        set_interface_language(spec.locale.value)

    async def _recover_finished(self, job: QueuedJob) -> None:
        spec = self._recovered_spec(job)
        self._enter_job_context(spec)
        hooks = self._hooks_factory.for_spec(spec) if self._hooks_factory is not None else None
        await self._finish(spec, job, hooks)

    def _adopt(self, job: QueuedJob) -> int:
        spec = self._recovered_spec(job)
        hooks = self._hooks_factory.for_spec(spec) if self._hooks_factory is not None else None
        if hooks is None:
            return 0
        self._in_flight[spec.id] = spec
        task = asyncio.create_task(self._drive_adopted(spec, hooks))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return 1

    async def _drive_adopted(self, spec: JobSpec, hooks: IJobHooks) -> None:
        self._enter_job_context(spec)
        try:
            await self._follow_compile(spec, hooks)
        except Exception:
            logger.exception("recovered compile failed", compile_id=str(spec.id))
        finally:
            self._in_flight.pop(spec.id, None)
            self._cancelled.discard(spec.id)

    # --- activity ---

    def is_active(self, job_id: UUID) -> bool:
        return job_id in self._in_flight

    def has_any_active(self) -> bool:
        return any(job_kind_spec(spec.kind).policy.counts_as_active for spec in self._in_flight.values())

    def has_active_for_folder(self, folder: Path) -> bool:
        return any(
            job_kind_spec(spec.kind).policy.blocks_folder_ops
            and spec.local_root is not None
            and _same_folder(spec.local_root, folder)
            for spec in self._in_flight.values()
        )

    # --- staging and enqueue ---

    async def _stage_and_enqueue(self, spec: JobSpec, timeout_s: float | None) -> QueuedJob | None:
        """Манифест, затем постановка; `None`, если задачу отменили, пока шла подготовка."""
        user_id = _user_id(spec.actor)
        folder = _folder_of(spec)
        paths = await asyncio.to_thread(_manifest_paths, spec, folder)
        manifest = await self._uploader.ensure(spec.project_id, folder, paths, self._limits)
        if spec.id in self._cancelled:
            return None
        policy = job_kind_spec(spec.kind).policy
        timeout = timeout_s or policy.default_timeout_s or DEFAULT_TIMEOUT_S
        role = await self._role_of(spec)
        spec = await self._with_user_passes(spec)
        envelope = JobEnvelope(
            spec=_without_root(spec),
            manifest=tuple(manifest),
            timeout_s=timeout,
            attempt=1,
            job_token="-",  # noqa: S106 — настоящий токен выдаётся раннеру при выдаче задачи
            actor_role=role,
        )
        payload = {k: v for k, v in encode_envelope(envelope).items() if k not in {"job_token", "attempt"}}
        outcome = await self._queue.enqueue(
            EnqueueRequest(
                job_id=spec.id,
                kind=spec.kind,
                project_id=spec.project_id,
                user_id=user_id,
                tags=spec.tags,
                payload=payload,
                priority_class=policy.priority_class,
                coalesce_key=_coalesce_key(spec),
                max_attempts=policy.max_attempts,
                timeout_s=timeout,
            )
        )
        return outcome.job

    async def _with_user_passes(self, spec: JobSpec) -> JobSpec:
        """Настройка `latex_passes` пользователя важнее значения из шаблона; у раннера своих настроек нет."""
        if self._settings_repo is None or spec.kind is not JobKind.compile:
            return spec
        payload = compile_payload_of(spec)
        try:
            stored = (await self._settings_repo.get()).get("latex_passes")
            passes = int(stored) if stored is not None else payload.default_passes
        except (TypeError, ValueError):
            return spec
        return replace(spec, payload=replace(payload, default_passes=passes))

    async def _role_of(self, spec: JobSpec) -> Role | None:
        if self._role_source is None:
            return None
        return await self._role_source(spec.actor, spec.project_id)

    # --- waiting ---

    async def _wait(self, job_id: UUID, on_claimed: Callable[[], Awaitable[bool]] | None) -> QueuedJob | None:
        """Ждёт терминальное состояние; `on_claimed` вызывается один раз, когда раннер взял задачу.

        `None` возвращается, если `on_claimed` ответил False либо записи очереди не стало.
        """
        claimed = False
        while True:
            job = await self._queue.get(job_id)
            if job is None:
                return None
            if on_claimed is not None and not claimed and job.attempt >= 1:
                # Быстрая задача могла закончиться между опросами: старт всё равно был.
                claimed = True
                if not await on_claimed():
                    return None
            if job.state.is_terminal:
                return job
            await asyncio.sleep(self._interval)

    def _result_of(self, spec: JobSpec, job: QueuedJob | None) -> JobResult:
        if job is None:
            error = JobError(JobErrorCategory.internal, ERROR_CODE_JOB_LOST, "queue record disappeared")
            return JobResult(status=JobStatus.failed, error=error)
        if job.result is not None:
            # Выходы в записи лежат рядом с итогом: их применяет отдельный шаг, кодек их не знает.
            return decode_result(spec.kind, {k: v for k, v in job.result.items() if k != "artifacts"})
        code = job.error_code
        match job.state:
            case JobState.cancelled:
                return _unfinished(spec, JobStatus.cancelled, code)
            case JobState.timed_out:
                return _unfinished(spec, JobStatus.timed_out, code or ERROR_CODE_TIMED_OUT)
            case JobState.succeeded:
                return _unfinished(spec, JobStatus.failed, ERROR_CODE_JOB_LOST)
            case _:
                return _unfinished(spec, JobStatus.failed, code or ERROR_CODE_JOB_LOST)


def _unfinished(spec: JobSpec, status: JobStatus, code: str | None) -> JobResult:
    """Итог без результата раннера: отмена, замена более новой сборкой, потеря раннера, таймаут."""
    data = CompileResult(build_ok=False, finished_at=_utc_now()) if spec.kind is JobKind.compile else None
    error = _error_of(status, code)
    return JobResult(status=status, data=data, error=error)


def _error_of(status: JobStatus, code: str | None) -> JobError | None:
    if status is JobStatus.cancelled and code is None:
        return None
    category = JobErrorCategory.unavailable if code == RunnerErrorCode.runner_lost.value else JobErrorCategory.internal
    return JobError(category, code or ERROR_CODE_CANCELLED)


def _apply_failure(spec: JobSpec, exc: ApplyError) -> JobResult:
    error = JobError(JobErrorCategory.internal, exc.code, exc.detail)
    data = CompileResult(build_ok=False, finished_at=_utc_now()) if spec.kind is JobKind.compile else None
    return JobResult(status=JobStatus.failed, data=data, error=error)


def _artifacts_of(job: QueuedJob) -> tuple[ArtifactRef, ...]:
    raw = (job.result or {}).get("artifacts") or ()
    return decode(tuple[ArtifactRef, ...], raw)


def _staging_failure(spec: JobSpec, exc: Exception) -> JobResult:
    if isinstance(exc, ManifestError):
        error = JobError(JobErrorCategory.invalid_input, exc.code, str(exc))
    else:
        error = JobError(JobErrorCategory.internal, ERROR_CODE_STAGING_FAILED, str(exc))
    data = CompileResult(build_ok=False, finished_at=_utc_now()) if spec.kind is JobKind.compile else None
    return JobResult(status=JobStatus.failed, data=data, error=error)


def _user_id(actor: Actor) -> UUID:
    if actor.kind is not ActorKind.user or actor.id is None:
        raise ActorRequired("задача очереди ставится только от имени пользователя")
    try:
        return UUID(actor.id)
    except ValueError as exc:
        raise ActorRequired(f"неверный id пользователя: {actor.id!r}") from exc


def _folder_of(spec: JobSpec) -> Path:
    if spec.local_root is None:
        raise ValueError(f"job {spec.id} has no local_root")
    return spec.local_root


def _without_root(spec: JobSpec) -> JobSpec:
    return replace(spec, local_root=None)


def _coalesce_key(spec: JobSpec) -> str | None:
    """Новая сборка документа заменяет не начатую сборку того же документа."""
    if spec.kind is not JobKind.compile:
        return None
    return f"compile:{spec.project_id}:{compile_payload_of(spec).doc_id}"


def _manifest_paths(spec: JobSpec, folder: Path) -> Sequence[str]:
    """Что раннеру нужно из проекта: для сборки весь проект, для остальных видов файлы из нагрузки."""
    payload: Any = spec.payload
    match spec.kind:
        case JobKind.compile:
            return _project_files(folder)
        case JobKind.office_convert:
            assert isinstance(payload, OfficeConvertPayload)  # noqa: S101
            return (payload.source.path,)
        case JobKind.verify_detached:
            assert isinstance(payload, VerifyDetachedPayload)  # noqa: S101
            return (payload.pdf.path,)
        case JobKind.pack_submission:
            assert isinstance(payload, PackSubmissionPayload)  # noqa: S101
            return tuple(file.path for file in payload.manifest_files())
    raise ValueError(f"no manifest for job kind {spec.kind}")


def _project_files(folder: Path) -> list[str]:
    """Обычные файлы проекта без служебных папок; симлинки в манифест не входят."""
    found: list[str] = []
    for current, dirs, files in os.walk(folder, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS)
        base = Path(current)
        for name in sorted(files):
            try:
                mode = (base / name).lstat().st_mode
            except OSError:
                continue
            if stat.S_ISREG(mode):
                found.append((base / name).relative_to(folder).as_posix())
    return found


def _same_folder(left: Path, right: Path) -> bool:
    with contextlib.suppress(OSError):
        return left.resolve() == right.resolve()
    return left == right
