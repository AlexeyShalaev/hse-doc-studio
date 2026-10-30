"""Долгий опрос перечитывает раннер: пауза и отзыв во время ожидания действуют сразу."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from hse_doc_studio.core.jobs.runners import Runner
from hse_doc_studio.core.jobs.wire import PollRequest
from hse_doc_studio.use_cases.jobs.runner_jobs import RunnerJobService

from tests.fakes.runners import InMemoryRunnerRepository

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def _service(runner: Runner) -> tuple[RunnerJobService, AsyncMock, InMemoryRunnerRepository]:
    runners = InMemoryRunnerRepository()
    await runners.add(runner)
    queue = AsyncMock()
    queue.claim.return_value = None
    service = RunnerJobService(
        queue, MagicMock(), runners, MagicMock(), AsyncMock(), lease_s=45, timeout_grace_s=10, poll_interval_s=0.01
    )
    return service, queue, runners


def _runner() -> Runner:
    return Runner(
        id=uuid4().hex,
        name="r",
        token_hash="h",
        tags=frozenset({"tex"}),
        concurrency=1,
        resource_class="standard",
        version="1",
        created_at=_NOW,
    )


async def test__poll__runner_revoked_after_authentication__claims_nothing() -> None:
    runner = _runner()
    service, queue, runners = await _service(runner)
    await runners.revoke(runner.id, _NOW)

    response = await service.poll(runner, PollRequest(wait_s=0))

    assert response.envelope is None
    queue.claim.assert_not_called()


async def test__poll__runner_paused_after_authentication__claims_nothing() -> None:
    runner = _runner()
    service, queue, runners = await _service(runner)
    await runners.set_paused(runner.id, True)

    response = await service.poll(replace(runner, paused=False), PollRequest(wait_s=0))

    assert response.envelope is None
    queue.claim.assert_not_called()
