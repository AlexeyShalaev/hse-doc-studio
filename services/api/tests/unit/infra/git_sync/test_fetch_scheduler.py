from __future__ import annotations

import asyncio
import threading
from contextlib import suppress

import structlog.testing
from hse_doc_studio.infra.git_sync.fetch_scheduler import GitFetchScheduler
from hse_doc_studio.use_cases.git_sync.fetch_all_remotes import FetchTickResult

_BUSY = FetchTickResult(registered=2, fetched=1)
_EMPTY = FetchTickResult()


class _Waits:
    """Подмена ожидания: записывает запрошенные паузы и останавливает цикл после заданного числа."""

    def __init__(self, stop_after: int) -> None:
        self.delays: list[float] = []
        self._stop_after = stop_after

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)
        if len(self.delays) >= self._stop_after:
            raise asyncio.CancelledError


async def _run(scheduler: GitFetchScheduler) -> None:
    with suppress(asyncio.CancelledError):
        await scheduler.loop()


async def test__loop__waits_the_startup_delay_then_ticks_every_tick_s() -> None:
    waits = _Waits(stop_after=3)
    ticks = 0

    async def tick() -> FetchTickResult:
        nonlocal ticks
        ticks += 1
        return _BUSY

    await _run(GitFetchScheduler(tick, tick_s=30, startup_delay_s=60, idle_s=600, wait=waits))

    assert waits.delays == [60, 30, 30]
    assert ticks == 2


async def test__loop__no_registered_projects__sleeps_long() -> None:
    waits = _Waits(stop_after=3)

    async def tick() -> FetchTickResult:
        return _EMPTY

    await _run(GitFetchScheduler(tick, tick_s=30, startup_delay_s=1, idle_s=600, wait=waits))

    assert waits.delays == [1, 600, 600]


async def test__loop__a_project_appears__goes_back_to_the_short_tick() -> None:
    waits = _Waits(stop_after=4)
    results = iter([_EMPTY, _BUSY, _BUSY])

    async def tick() -> FetchTickResult:
        return next(results)

    await _run(GitFetchScheduler(tick, tick_s=30, startup_delay_s=0, idle_s=600, wait=waits))

    assert waits.delays == [0, 600, 30, 30]


async def test__loop__failing_tick__keeps_the_loop_alive() -> None:
    waits = _Waits(stop_after=4)
    calls = 0

    async def tick() -> FetchTickResult:
        nonlocal calls
        calls += 1
        raise RuntimeError("сбой тика")

    await _run(GitFetchScheduler(tick, tick_s=30, startup_delay_s=0, wait=waits))

    assert calls == 3
    assert waits.delays == [0, 30, 30, 30]


async def test__loop__failing_ticks__are_logged_once_per_streak() -> None:
    waits = _Waits(stop_after=6)
    outcomes: list[object] = [RuntimeError("1"), RuntimeError("2"), _BUSY, RuntimeError("3")]

    async def tick() -> FetchTickResult:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return _BUSY

    with structlog.testing.capture_logs() as logs:
        await _run(GitFetchScheduler(tick, tick_s=30, startup_delay_s=0, wait=waits))

    failures = [entry for entry in logs if entry["event"] == "git fetch tick failed"]
    assert len(failures) == 2


async def test__loop__cancellation_during_a_tick__is_not_swallowed() -> None:
    async def tick() -> FetchTickResult:
        await asyncio.sleep(10)
        return _BUSY

    scheduler = GitFetchScheduler(tick, tick_s=30, startup_delay_s=0, wait=_Waits(stop_after=99))
    task = asyncio.create_task(scheduler.loop())
    await asyncio.sleep(0.02)
    task.cancel()

    with suppress(asyncio.CancelledError):
        await task
    assert task.cancelled()


async def test__loop__real_wait__startup_delay_is_respected() -> None:
    ticks = 0

    async def tick() -> FetchTickResult:
        nonlocal ticks
        ticks += 1
        return _BUSY

    scheduler = GitFetchScheduler(tick, tick_s=0.01, startup_delay_s=10)
    task = asyncio.create_task(scheduler.loop())
    await asyncio.sleep(0.05)
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

    assert ticks == 0


async def test__wake__ends_the_idle_sleep_at_once() -> None:
    ticks = 0
    second_tick = asyncio.Event()

    async def tick() -> FetchTickResult:
        nonlocal ticks
        ticks += 1
        if ticks == 2:
            second_tick.set()
        return _EMPTY

    scheduler = GitFetchScheduler(tick, tick_s=30, startup_delay_s=0, idle_s=600)
    task = asyncio.create_task(scheduler.loop())
    await asyncio.sleep(0.05)
    assert ticks == 1

    scheduler.wake()
    await asyncio.wait_for(second_tick.wait(), timeout=2)
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

    assert ticks == 2


async def test__wake__from_another_thread__is_delivered() -> None:
    ticks = 0
    second_tick = asyncio.Event()

    async def tick() -> FetchTickResult:
        nonlocal ticks
        ticks += 1
        if ticks == 2:
            second_tick.set()
        return _EMPTY

    scheduler = GitFetchScheduler(tick, tick_s=30, startup_delay_s=0, idle_s=600)
    task = asyncio.create_task(scheduler.loop())
    await asyncio.sleep(0.05)

    threading.Thread(target=scheduler.wake).start()
    await asyncio.wait_for(second_tick.wait(), timeout=2)
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

    assert ticks == 2


async def test__wake__before_the_loop_started__shortens_the_startup_delay() -> None:
    first_tick = asyncio.Event()

    async def tick() -> FetchTickResult:
        first_tick.set()
        return _EMPTY

    scheduler = GitFetchScheduler(tick, tick_s=30, startup_delay_s=60, idle_s=600)
    scheduler.wake()
    task = asyncio.create_task(scheduler.loop())

    await asyncio.wait_for(first_tick.wait(), timeout=2)
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def test__wake__after_the_loop_is_gone__does_not_raise() -> None:
    async def tick() -> FetchTickResult:
        return _EMPTY

    scheduler = GitFetchScheduler(tick, tick_s=30, startup_delay_s=0)

    async def start_and_stop() -> None:
        task = asyncio.create_task(scheduler.loop())
        await asyncio.sleep(0.01)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    asyncio.run(start_and_stop())

    scheduler.wake()
