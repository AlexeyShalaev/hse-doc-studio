"""Лимит одновременных docker-сборок (CompileConcurrencyLimiter)."""

from __future__ import annotations

import asyncio

import pytest
from hse_doc_studio.infra.compile.concurrency import CompileConcurrencyLimiter


async def _hold_slot(
    limiter: CompileConcurrencyLimiter,
    limit: int,
    release: asyncio.Event,
    peak: list[int],
) -> None:
    async with limiter.slot(limit):
        peak.append(limiter.active)
        await release.wait()


@pytest.mark.asyncio
async def test__slot__caps_concurrency_and_queues_the_rest() -> None:
    limiter = CompileConcurrencyLimiter()
    release = asyncio.Event()
    peak: list[int] = []

    tasks = [asyncio.create_task(_hold_slot(limiter, 2, release, peak)) for _ in range(5)]
    await asyncio.sleep(0.05)

    # Ровно два держат слот, трое ждут в очереди (не упали, не запустились).
    assert limiter.active == 2

    release.set()
    await asyncio.gather(*tasks)
    assert limiter.active == 0
    # Ни один захват не видел больше двух активных.
    assert len(peak) == 5
    assert max(peak) <= 2


@pytest.mark.asyncio
async def test__slot__released_on_cancel_wakes_waiter() -> None:
    limiter = CompileConcurrencyLimiter()
    forever = asyncio.Event()
    peak: list[int] = []

    holder = asyncio.create_task(_hold_slot(limiter, 1, forever, peak))
    await asyncio.sleep(0.02)
    assert limiter.active == 1

    entered = asyncio.Event()

    async def waiter() -> None:
        async with limiter.slot(1):
            entered.set()

    waiting = asyncio.create_task(waiter())
    await asyncio.sleep(0.02)
    assert not entered.is_set()

    # Отмена держателя (аналог отмены сборки) освобождает слот очереди.
    holder.cancel()
    await asyncio.wait_for(waiting, timeout=1)
    assert entered.is_set()
    assert limiter.active == 0


@pytest.mark.asyncio
async def test__slot__cancelled_while_waiting_does_not_leak() -> None:
    limiter = CompileConcurrencyLimiter()
    release = asyncio.Event()
    peak: list[int] = []

    holder = asyncio.create_task(_hold_slot(limiter, 1, release, peak))
    await asyncio.sleep(0.02)

    waiting = asyncio.create_task(_hold_slot(limiter, 1, release, peak))
    await asyncio.sleep(0.02)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting

    # Ожидавший отменён ДО захвата — счётчик не протёк.
    assert limiter.active == 1
    release.set()
    await holder
    assert limiter.active == 0
