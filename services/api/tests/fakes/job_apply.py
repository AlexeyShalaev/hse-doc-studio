"""Метка применённого итога задач поверх InMemoryJobQueue."""

from __future__ import annotations

from uuid import UUID

from hse_doc_studio.core.jobs.queue import QueuedJob

from tests.fakes.job_queue import InMemoryJobQueue


class InMemoryApplyLedger:
    def __init__(self, queue: InMemoryJobQueue) -> None:
        self._queue = queue
        self.applied: set[UUID] = set()

    async def mark_applied(self, job_id: UUID) -> bool:
        job = await self._queue.get(job_id)
        if job is None or not job.state.is_terminal or job_id in self.applied:
            return False
        self.applied.add(job_id)
        return True

    async def list_unapplied(self) -> tuple[QueuedJob, ...]:
        return tuple(job for job in await self._queue.list() if job.state.is_terminal and job.id not in self.applied)
