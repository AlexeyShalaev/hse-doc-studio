"""Ход установок в памяти процесса: шаги, итог и ошибка без секретов. Хватает на один процесс api."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import uuid4

from hse_doc_studio.core.identity.session_policy import utc_now
from hse_doc_studio.core.runner_install.entities import (
    InstallJob,
    InstallJobState,
    InstallStep,
    InstallStepState,
    InstallTarget,
)

MAX_JOBS = 50
JOB_TTL = timedelta(hours=2)


class InstallJobStore:
    def __init__(self, *, clock: Callable[[], datetime] = utc_now) -> None:
        self._clock = clock
        self._jobs: dict[str, InstallJob] = {}

    def create(self, target: InstallTarget, name: str, actor_id: str, step_keys: tuple[str, ...]) -> InstallJob:
        self._evict()
        job = InstallJob(
            id=uuid4().hex,
            target=target,
            name=name,
            created_by=actor_id,
            created_at=self._clock(),
            steps=[InstallStep(key) for key in step_keys],
        )
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> InstallJob | None:
        self._evict()
        return self._jobs.get(job_id)

    def running(self, target: InstallTarget) -> InstallJob | None:
        return next((j for j in self._jobs.values() if j.target is target and j.state is InstallJobState.running), None)

    def set_step(self, job: InstallJob, key: str, state: InstallStepState, detail: str = "") -> None:
        step = job.step(key)
        step.state = state
        step.detail = detail

    def _evict(self) -> None:
        now = self._clock()
        for job_id in [
            i for i, j in self._jobs.items() if now - j.created_at > JOB_TTL and j.state is not InstallJobState.running
        ]:
            del self._jobs[job_id]
        while len(self._jobs) > MAX_JOBS:
            oldest = min(self._jobs.values(), key=lambda j: j.created_at)
            if oldest.state is InstallJobState.running:
                break
            del self._jobs[oldest.id]
