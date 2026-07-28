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
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Literal

import structlog

from hse_doc_studio.infra.docker.system_manager import DockerSystemManager

logger = structlog.get_logger()

StepKind = Literal["build_cache", "dangling_images", "image", "container"]
StepStatus = Literal["pending", "running", "done", "error", "skipped"]
JobStatus = Literal["running", "cancelling", "done", "cancelled", "error"]


@dataclass
class CleanupStep:
    kind: StepKind
    # Image reference or container name; None for the prune steps.
    ref: str | None = None
    status: StepStatus = "pending"
    freed_bytes: int = 0
    error: str | None = None


@dataclass
class CleanupJob:
    id: str
    status: JobStatus
    steps: list[CleanupStep]
    freed_bytes: int = 0
    task: asyncio.Task[None] | None = field(default=None, repr=False)


class CleanupBusyError(Exception):
    """A cleanup job is already running."""


class DockerCleanupJobManager:
    def __init__(self, manager: DockerSystemManager) -> None:
        self._manager = manager
        self._job: CleanupJob | None = None
        self._lock = asyncio.Lock()

    async def start(self, steps: list[CleanupStep]) -> CleanupJob:
        async with self._lock:
            if self._job is not None and self._job.status in ("running", "cancelling"):
                raise CleanupBusyError
            job = CleanupJob(id=uuid.uuid4().hex, status="running", steps=steps)
            self._job = job
            job.task = asyncio.create_task(self._run(job))
            return job

    def current(self) -> CleanupJob | None:
        return self._job

    def cancel(self) -> CleanupJob | None:
        job = self._job
        if job is None or job.status not in ("running", "cancelling"):
            return None
        job.status = "cancelling"
        return job

    async def _run(self, job: CleanupJob) -> None:
        had_error = False
        try:
            for step in job.steps:
                if job.status == "cancelling":
                    step.status = "skipped"
                    continue
                step.status = "running"
                result = await self._execute(step)
                step.freed_bytes = result[0]
                step.error = result[1]
                step.status = "error" if step.error else "done"
                had_error = had_error or step.error is not None
                job.freed_bytes += step.freed_bytes
        except Exception as exc:  # noqa: BLE001 — a background task must never crash the loop
            logger.warning("docker cleanup job crashed", error_type=type(exc).__name__)
            for step in job.steps:
                if step.status in ("pending", "running"):
                    step.status = "skipped"
            job.status = "error"
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

    async def _execute(self, step: CleanupStep) -> tuple[int, str | None]:
        """Run one step; returns (freed_bytes, error)."""
        if step.kind == "build_cache":
            result = await self._manager.prune_build_cache()
        elif step.kind == "dangling_images":
            result = await self._manager.prune_dangling_images()
        elif step.kind == "image":
            result = await self._manager.remove_images([step.ref or ""], target="image")
        else:
            result = await self._manager.remove_stopped_managed_container(step.ref or "")
        error = result.errors[0] if result.errors else None
        return result.freed_bytes, error
