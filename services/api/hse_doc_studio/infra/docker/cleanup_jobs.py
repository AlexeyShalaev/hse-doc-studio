"""Background docker-cleanup job: step-by-step progress + cancellation.

A cleanup can take minutes (`docker builder prune` on gigabytes, an 8 GB image
removal), so it runs as ONE app-scoped background task the UI polls — the same
pattern as the Ollama pull jobs. The plan is expanded to individual steps
up-front (each image / container is its own step) so the UI shows granular
progress and «Отменить» takes effect between steps: the docker command already
in flight finishes (killing `builder prune` mid-run is pointless — freed space
stays freed), everything still pending is skipped.

Only one cleanup runs at a time; the last finished job is kept for display
until the next one starts.

Виды шагов подключаемые: четыре шага Docker (`DOCKER_STEP_KINDS`) менеджер умеет
сам, остальные передаёт процесс (`extra_steps`, у раннера шаги своего кэша).
Наблюдатель хода (`start(..., observer=...)`) получает задачу на каждой смене
статуса шага и в конце; его сбой очистку не останавливает.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Literal

import structlog

from hse_doc_studio.core.docker_disk.steps import DOCKER_STEP_KINDS, CleanupStep, DockerStepKind, StepStatus
from hse_doc_studio.infra.docker.system_manager import DockerSystemManager

logger = structlog.get_logger()

__all__ = [
    "CleanupBusyError",
    "CleanupJob",
    "CleanupObserver",
    "CleanupStep",
    "DockerCleanupJobManager",
    "DockerStepKind",
    "JobStatus",
    "StepOutcome",
    "StepRunner",
    "StepStatus",
]

JobStatus = Literal["running", "cancelling", "done", "cancelled", "error"]


@dataclass(frozen=True)
class StepOutcome:
    freed_bytes: int
    # Одна строка до 300 символов; None, если шаг удался.
    error: str | None = None


# Исполнитель подключённого вида шага. Исключение превращается в ошибку шага с именем его типа.
StepRunner = Callable[[CleanupStep], Awaitable[StepOutcome]]


@dataclass
class CleanupJob:
    id: str
    status: JobStatus
    steps: list[CleanupStep]
    freed_bytes: int = 0
    task: asyncio.Task[None] | None = field(default=None, repr=False)


# Наблюдатель хода: вызывается после каждой смены статуса шага и после итога, задача та же
# (изменяемая), поэтому нужное из неё берётся до первого `await`. Долгую доставку (HTTP)
# наблюдатель уводит в свою задачу: пока он ждёт, следующий шаг не начнётся.
CleanupObserver = Callable[[CleanupJob], Awaitable[None]]


class CleanupBusyError(Exception):
    """A cleanup job is already running."""


class DockerCleanupJobManager:
    def __init__(self, manager: DockerSystemManager, extra_steps: Mapping[str, StepRunner] | None = None) -> None:
        extra = dict(extra_steps or {})
        overlap = DOCKER_STEP_KINDS & extra.keys()
        if overlap:
            # Шаги Docker проверены правилами «Диска»; подменить их подключением нельзя.
            raise ValueError(f"step kinds already built in: {sorted(overlap)}")
        self._manager = manager
        self._extra_steps = extra
        self._job: CleanupJob | None = None
        self._lock = asyncio.Lock()

    @property
    def step_kinds(self) -> frozenset[str]:
        return DOCKER_STEP_KINDS | self._extra_steps.keys()

    async def start(self, steps: list[CleanupStep], *, observer: CleanupObserver | None = None) -> CleanupJob:
        async with self._lock:
            if self._job is not None and self._job.status in ("running", "cancelling"):
                raise CleanupBusyError
            job = CleanupJob(id=uuid.uuid4().hex, status="running", steps=steps)
            self._job = job
            job.task = asyncio.create_task(self._run(job, observer))
            return job

    def current(self) -> CleanupJob | None:
        return self._job

    def cancel(self) -> CleanupJob | None:
        job = self._job
        if job is None or job.status not in ("running", "cancelling"):
            return None
        job.status = "cancelling"
        return job

    async def _run(self, job: CleanupJob, observer: CleanupObserver | None) -> None:
        had_error = False
        try:
            for step in job.steps:
                if job.status == "cancelling":
                    step.status = "skipped"
                    continue
                step.status = "running"
                await _notify(observer, job)
                outcome = await self._execute(step)
                step.freed_bytes = outcome.freed_bytes
                step.error = outcome.error
                step.status = "error" if step.error else "done"
                had_error = had_error or step.error is not None
                job.freed_bytes += step.freed_bytes
                await _notify(observer, job)
        except Exception as exc:  # noqa: BLE001 — a background task must never crash the loop
            logger.warning("docker cleanup job crashed", error_type=type(exc).__name__)
            for step in job.steps:
                if step.status in ("pending", "running"):
                    step.status = "skipped"
            job.status = "error"
            await _notify(observer, job)
            return
        if job.status == "cancelling":
            job.status = "cancelled"
        else:
            job.status = "error" if had_error else "done"
        logger.info(
            "docker cleanup job finished",
            status=job.status,
            freed_bytes=job.freed_bytes,
            steps=len(job.steps),
        )
        await _notify(observer, job)

    async def _execute(self, step: CleanupStep) -> StepOutcome:
        """Run one step; an exception becomes the step's error, the rest of the plan goes on."""
        try:
            if step.kind in DOCKER_STEP_KINDS:
                return await self._execute_docker(step)
            runner = self._extra_steps.get(step.kind)
            if runner is None:
                return StepOutcome(freed_bytes=0, error=f"unknown step kind: {step.kind}"[:300])
            return await runner(step)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — one failed step must not stop the others
            logger.warning("docker cleanup step failed", kind=step.kind, error_type=type(exc).__name__)
            return StepOutcome(freed_bytes=0, error=type(exc).__name__)

    async def _execute_docker(self, step: CleanupStep) -> StepOutcome:
        if step.kind == "build_cache":
            result = await self._manager.prune_build_cache()
        elif step.kind == "dangling_images":
            result = await self._manager.prune_dangling_images()
        elif step.kind == "image":
            result = await self._manager.remove_images([step.ref or ""], target="image")
        else:
            result = await self._manager.remove_stopped_managed_container(step.ref or "")
        return StepOutcome(freed_bytes=result.freed_bytes, error=result.errors[0] if result.errors else None)


async def _notify(observer: CleanupObserver | None, job: CleanupJob) -> None:
    if observer is None:
        return
    try:
        await observer(job)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 — a progress report must never stop the cleanup
        logger.warning("docker cleanup observer failed", error_type=type(exc).__name__)
