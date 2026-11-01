"""Опрос раннера передаёт очереди квоты установки; без источника выдача идёт без лимитов, как раньше."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from hse_doc_studio.core.jobs.queue import RunnerRef
from hse_doc_studio.core.jobs.runners import JobTokenSigner, Runner
from hse_doc_studio.core.jobs.scheduler import QueueQuota
from hse_doc_studio.core.jobs.wire import PollRequest
from hse_doc_studio.use_cases.jobs.runner_jobs import RunnerJobService
from hse_doc_studio.use_cases.jobs.wakeup import JobWakeup

from tests.fakes.runners import InMemoryRunnerRepository

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)


class _RecordingQueue:
    def __init__(self) -> None:
        self.quotas: list[QueueQuota | None] = []

    async def claim(self, runner: RunnerRef, *, lease_s: float, quota: QueueQuota | None = None) -> None:
        self.quotas.append(quota)


def _service(queue: _RecordingQueue, runners: InMemoryRunnerRepository, **kwargs: Any) -> RunnerJobService:
    return RunnerJobService(
        queue,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        runners,
        JobTokenSigner([b"k" * 32]),
        JobWakeup(),
        lease_s=45.0,
        timeout_grace_s=15.0,
        clock=lambda: NOW,
        **kwargs,
    )


async def _runner(runners: InMemoryRunnerRepository) -> Runner:
    runner = Runner(
        id=("a" * 32),
        name="r",
        token_hash="h",
        tags=frozenset({"tex"}),
        concurrency=1,
        resource_class="standard",
        version="1",
        created_at=NOW,
    )
    await runners.add(runner)
    return runner


async def test__poll__quota_source__limits_reach_the_queue() -> None:
    queue, runners = _RecordingQueue(), InMemoryRunnerRepository()
    limits = QueueQuota(max_running_per_user=2)

    async def source() -> QueueQuota | None:
        return limits

    service = _service(queue, runners, quota_source=source)

    await service.poll(await _runner(runners), PollRequest(wait_s=0))

    assert queue.quotas == [limits]


async def test__poll__no_quota_source__claims_unlimited() -> None:
    queue, runners = _RecordingQueue(), InMemoryRunnerRepository()
    service = _service(queue, runners)

    await service.poll(await _runner(runners), PollRequest(wait_s=0))

    assert queue.quotas == [None]
