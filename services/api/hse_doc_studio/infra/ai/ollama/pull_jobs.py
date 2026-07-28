from __future__ import annotations

import asyncio
from dataclasses import dataclass

import structlog

from hse_doc_studio.core.ai_runtime import IOllamaRuntime
from hse_doc_studio.core.entities import PullJob
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.i18n import current_interface_language

logger = structlog.get_logger()

# Status strings shown in the «Локальные модели» pull list. Resolved at the
# moment they are set — `start()` runs in the request context and the background
# `_run()` task inherits that context — so they follow the interface language
# that was active when the download began.
_PREPARING = {Lang.ru: "Подготовка…", Lang.en: "Preparing…"}
_DONE = {Lang.ru: "Готово", Lang.en: "Done"}
_TOO_MANY = {
    Lang.ru: "уже идёт максимум загрузок ({count}); дождитесь завершения",
    Lang.en: "the maximum number of downloads ({count}) is already running; wait for them to finish",
}


def _msg(mapping: dict[Lang, str]) -> str:
    return mapping.get(current_interface_language(), mapping[Lang.ru])


@dataclass
class _Job:
    name: str
    state: str = "running"  # running | success | failure
    message: str = ""
    error: str | None = None
    task: asyncio.Task[None] | None = None


def _snapshot(job: _Job) -> PullJob:
    return PullJob(name=job.name, state=job.state, message=job.message, error=job.error)


class PullModelJobManager:
    """Runs `ollama pull` in background tasks, decoupled from any request.

    A pull keeps running after the UI closes the modal or the tab — the task
    lives on the app event loop (this manager is an app-scoped singleton). The
    UI polls `list_jobs()` for progress and can reconnect freely. Already-pulled
    layers are cached by Ollama, so even a killed task resumes cheaply on retry.
    """

    def __init__(self, runtime: IOllamaRuntime, max_concurrent: int = 2) -> None:
        self._runtime = runtime
        self._max_concurrent = max_concurrent
        self._jobs: dict[str, _Job] = {}
        self._lock = asyncio.Lock()

    async def start(self, name: str) -> PullJob:
        async with self._lock:
            existing = self._jobs.get(name)
            if existing is not None and existing.state == "running":
                return _snapshot(existing)  # idempotent: one job per model
            running = sum(1 for j in self._jobs.values() if j.state == "running")
            if running >= self._max_concurrent:
                raise ValueError(_msg(_TOO_MANY).format(count=self._max_concurrent))
            job = _Job(name=name, message=_msg(_PREPARING))
            self._jobs[name] = job
            job.task = asyncio.create_task(self._run(job))
            return _snapshot(job)

    async def _run(self, job: _Job) -> None:
        try:
            stream = await self._runtime.pull_model(job.name)
            failed = False
            async for line in stream:
                if line == "__DONE__":
                    break
                if line == "__FAILED__":
                    failed = True
                    break
                job.message = line
            if failed:
                job.state = "failure"
                job.error = job.message
            else:
                job.state = "success"
                job.message = _msg(_DONE)
        except Exception as exc:  # noqa: BLE001 — a background task must never crash the loop
            logger.warning("ollama pull job failed", name=job.name, error_type=type(exc).__name__)
            job.state = "failure"
            job.error = type(exc).__name__

    def list_jobs(self) -> list[PullJob]:
        return [_snapshot(j) for j in self._jobs.values()]

    def dismiss(self, name: str) -> None:
        # Only finished jobs can be dismissed; a running pull is left alone.
        job = self._jobs.get(name)
        if job is not None and job.state != "running":
            self._jobs.pop(name, None)
