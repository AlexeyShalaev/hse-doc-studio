from __future__ import annotations

import asyncio

import pytest
from hse_doc_studio.core.background import AlwaysLeader, BackgroundTaskRunner, PeriodicTask


class SharedLock:
    """Один лок на несколько раннеров: как advisory-лок одной базы."""

    def __init__(self) -> None:
        self.owner: object | None = None

    def handle(self) -> _Handle:
        return _Handle(self)


class _Handle:
    def __init__(self, shared: SharedLock) -> None:
        self._shared = shared

    async def acquire(self) -> bool:
        if self._shared.owner in (None, self):
            self._shared.owner = self
            return True
        return False

    async def is_held(self) -> bool:
        return self._shared.owner is self

    async def release(self) -> None:
        if self._shared.owner is self:
            self._shared.owner = None


async def _until(predicate, timeout: float = 2.0) -> None:
    async def wait() -> None:
        while not predicate():
            await asyncio.sleep(0.005)

    await asyncio.wait_for(wait(), timeout)


async def test__two_instances__only_leader_runs_tasks() -> None:
    shared = SharedLock()
    calls: dict[str, int] = {"a": 0, "b": 0}

    def make(name: str) -> BackgroundTaskRunner:
        async def tick() -> None:
            calls[name] += 1

        runner = BackgroundTaskRunner(shared.handle(), leader_retry_s=0.01)
        runner.register(PeriodicTask("tick", 0.01, tick))
        return runner

    first, second = make("a"), make("b")
    first.start()
    await _until(lambda: first.is_leader)
    second.start()
    await _until(lambda: calls["a"] >= 3)

    assert not second.is_leader
    assert calls["b"] == 0

    await first.stop()
    await _until(lambda: second.is_leader)
    await _until(lambda: calls["b"] >= 1)
    await second.stop()


async def test__leader_lost__tasks_stop_and_other_instance_takes_over() -> None:
    shared = SharedLock()
    first = BackgroundTaskRunner(shared.handle(), leader_retry_s=0.01)
    second = BackgroundTaskRunner(shared.handle(), leader_retry_s=0.01)
    ran = {"first": 0, "second": 0}

    async def tick_first() -> None:
        ran["first"] += 1

    async def tick_second() -> None:
        ran["second"] += 1

    first.register(PeriodicTask("t", 0.01, tick_first))
    second.register(PeriodicTask("t", 0.01, tick_second))
    first.start()
    await _until(lambda: first.is_leader)
    second.start()

    shared.owner = object()
    await _until(lambda: not first.is_leader)
    frozen = ran["first"]
    shared.owner = None
    await _until(lambda: second.is_leader or first.is_leader)
    await asyncio.sleep(0.05)

    assert first.is_leader != second.is_leader
    assert ran["first"] - frozen <= 1 or first.is_leader
    await first.stop()
    await second.stop()


async def test__stop__waits_for_running_task() -> None:
    started = asyncio.Event()
    finished = asyncio.Event()

    async def slow() -> None:
        started.set()
        await asyncio.sleep(0.1)
        finished.set()

    runner = BackgroundTaskRunner(AlwaysLeader(), leader_retry_s=0.01)
    runner.register(PeriodicTask("slow", 10, slow, run_on_start=True))
    runner.start()
    await asyncio.wait_for(started.wait(), 1)

    await runner.stop(timeout_s=2)

    assert finished.is_set()
    assert not runner.running


async def test__stop__timeout_cancels_stuck_task_and_releases_lock() -> None:
    shared = SharedLock()
    started = asyncio.Event()

    async def stuck() -> None:
        started.set()
        await asyncio.sleep(60)

    runner = BackgroundTaskRunner(shared.handle(), leader_retry_s=0.01)
    runner.register(PeriodicTask("stuck", 10, stuck, run_on_start=True))
    runner.start()
    await asyncio.wait_for(started.wait(), 1)

    await runner.stop(timeout_s=0.05)

    assert shared.owner is None
    assert not runner.is_leader


async def test__failing_task__is_counted_and_loop_continues() -> None:
    attempts = 0

    async def boom() -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("x")

    runner = BackgroundTaskRunner(AlwaysLeader(), leader_retry_s=0.01)
    runner.register(PeriodicTask("boom", 0.01, boom, run_on_start=True))
    runner.start()
    await _until(lambda: attempts >= 3)
    await runner.stop()

    stats = runner.stats()["boom"]
    assert stats.failures >= 3
    assert stats.runs >= 3


def test__register__duplicate_or_bad_interval__rejected() -> None:
    runner = BackgroundTaskRunner()

    async def noop() -> None:
        return None

    runner.register(PeriodicTask("t", 1, noop))
    with pytest.raises(ValueError, match="уже"):
        runner.register(PeriodicTask("t", 1, noop))
    with pytest.raises(ValueError, match="положительным"):
        runner.register(PeriodicTask("z", 0, noop))
