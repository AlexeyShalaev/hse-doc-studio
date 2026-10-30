"""Долгий опрос перечитывает раннер: пауза и отзыв во время ожидания действуют сразу."""

from __future__ import annotations

import asyncio
import time
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


class _SleepingWakeup:
    """Будильник, который действительно уступает цикл: долгий опрос ждёт, а тест успевает вмешаться."""

    async def wait(self, timeout_s: float) -> None:
        await asyncio.sleep(min(timeout_s, 0.01))


async def test__poll__runner_went_offline_while_waiting__ends_without_touching_or_claiming() -> None:
    """Мягкая остановка посреди долгого опроса: брошенный опрос не воскрешает раннер и не берёт задачу."""
    runner = _runner()
    runners = InMemoryRunnerRepository()
    await runners.add(runner)
    queue = AsyncMock()
    queue.claim.return_value = None
    service = RunnerJobService(
        queue,
        MagicMock(),
        runners,
        MagicMock(),
        _SleepingWakeup(),  # type: ignore[arg-type]
        lease_s=45,
        timeout_grace_s=10,
        poll_interval_s=0.01,
    )

    started = time.monotonic()
    polling = asyncio.create_task(service.poll(runner, PollRequest(wait_s=5)))
    await asyncio.sleep(0.1)
    offline_at = datetime.now(UTC)
    await runners.mark_offline(runner.id, offline_at)
    claims = queue.claim.await_count
    response = await asyncio.wait_for(polling, timeout=2)

    assert response.envelope is None
    assert time.monotonic() - started < 2
    assert queue.claim.await_count <= claims + 1
    current = await runners.get(runner.id)
    assert current is not None
    assert current.last_seen_at is not None
    assert current.last_seen_at <= offline_at


async def test__poll__client_disconnected__ends_without_claiming_or_touching() -> None:
    """Раннер убит без `/offline`: опрос, чей клиент отключился, задачу не берёт (иначе она ждала бы аренду)."""
    runner = _runner()
    runners = InMemoryRunnerRepository()
    await runners.add(runner)
    queue = AsyncMock()
    queue.claim.return_value = None
    service = RunnerJobService(
        queue,
        MagicMock(),
        runners,
        MagicMock(),
        _SleepingWakeup(),  # type: ignore[arg-type]
        lease_s=45,
        timeout_grace_s=10,
        poll_interval_s=0.01,
    )
    disconnected = False

    async def gone() -> bool:
        return disconnected

    polling = asyncio.create_task(service.poll(runner, PollRequest(wait_s=5), gone=gone))
    await asyncio.sleep(0.1)
    disconnected = True
    claims = queue.claim.await_count
    response = await asyncio.wait_for(polling, timeout=2)

    assert response.envelope is None
    assert queue.claim.await_count <= claims + 1
