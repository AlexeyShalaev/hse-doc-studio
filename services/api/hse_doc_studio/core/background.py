"""Реестр периодических фоновых задач с единственным лидером.

Периодика сервера (reaper, GC, чистка сессий, ретеншн аудита) должна идти ровно в одном экземпляре,
поэтому исполняет её только держатель ``ILeaderLock``. Остальные экземпляры раз в ``leader_retry_s``
пробуют перехватить лидерство и продолжают с того же места, когда лидер пропал.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

import structlog

logger = structlog.get_logger(__name__)


class ILeaderLock(Protocol):
    async def acquire(self) -> bool:
        """Попытаться стать лидером; не блокируется."""
        ...

    async def is_held(self) -> bool:
        """Лидерство всё ещё за нами (соединение с локом живо)."""
        ...

    async def release(self) -> None: ...


class AlwaysLeader:
    """Лидер без внешнего лока: для режима с одним процессом и для тестов."""

    async def acquire(self) -> bool:
        return True

    async def is_held(self) -> bool:
        return True

    async def release(self) -> None:
        return None


@dataclass(frozen=True)
class PeriodicTask:
    name: str
    interval_s: float
    run: Callable[[], Awaitable[None]]
    run_on_start: bool = False


@dataclass
class TaskStats:
    runs: int = 0
    failures: int = 0
    last_duration_s: float = 0.0
    total_duration_s: float = 0.0
    last_run_at: float | None = None


@dataclass
class _State:
    leader: bool = False
    stats: dict[str, TaskStats] = field(default_factory=dict)


class BackgroundTaskRunner:
    def __init__(self, leader: ILeaderLock | None = None, *, leader_retry_s: float = 5.0) -> None:
        self._lock: ILeaderLock = leader or AlwaysLeader()
        self._leader_retry_s = leader_retry_s
        self._tasks: dict[str, PeriodicTask] = {}
        self._state = _State()
        self._stop = asyncio.Event()
        self._supervisor: asyncio.Task[None] | None = None
        self._workers: dict[str, asyncio.Task[None]] = {}

    def use_leader_lock(self, leader: ILeaderLock) -> None:
        """Подменить лок до старта: движок БД доступен только после сборки контейнера."""
        if self.running:
            msg = "лок лидерства меняют до start()"
            raise RuntimeError(msg)
        self._lock = leader

    def register(self, task: PeriodicTask) -> None:
        if task.name in self._tasks:
            msg = f"фоновая задача {task.name} уже зарегистрирована"
            raise ValueError(msg)
        if task.interval_s <= 0:
            msg = f"интервал задачи {task.name} должен быть положительным"
            raise ValueError(msg)
        self._tasks[task.name] = task
        self._state.stats[task.name] = TaskStats()

    @property
    def is_leader(self) -> bool:
        return self._state.leader

    @property
    def running(self) -> bool:
        return self._supervisor is not None and not self._supervisor.done()

    def stats(self) -> dict[str, TaskStats]:
        return dict(self._state.stats)

    def start(self) -> None:
        if self.running:
            return
        self._stop = asyncio.Event()
        self._supervisor = asyncio.create_task(self._supervise(), name="background-supervisor")

    async def stop(self, timeout_s: float = 10.0) -> None:
        """Остановка: текущие прогоны дорабатывают до ``timeout_s``, остаток отменяется; лок отпускается."""
        self._stop.set()
        supervisor = self._supervisor
        if supervisor is not None:
            try:
                await asyncio.wait_for(asyncio.shield(supervisor), timeout=timeout_s)
            except TimeoutError:
                logger.warning("background_stop_timeout", timeout_s=timeout_s)
                supervisor.cancel()
                await asyncio.gather(supervisor, return_exceptions=True)
                await self._cancel_workers()
                await self._release_leadership()
        self._supervisor = None

    async def _supervise(self) -> None:
        try:
            while not self._stop.is_set():
                if self._state.leader:
                    if not await self._still_leader():
                        await self._lose_leadership()
                elif await self._try_lead():
                    self._gain_leadership()
                await self._sleep(self._leader_retry_s)
        finally:
            await self._shutdown_workers()

    async def _try_lead(self) -> bool:
        try:
            return await self._lock.acquire()
        except Exception:
            logger.exception("background_leader_acquire_failed")
            return False

    async def _still_leader(self) -> bool:
        try:
            return await self._lock.is_held()
        except Exception:
            logger.exception("background_leader_check_failed")
            return False

    def _gain_leadership(self) -> None:
        self._state.leader = True
        logger.info("background_leader_acquired")
        for task in self._tasks.values():
            self._workers[task.name] = asyncio.create_task(self._loop(task), name=f"background-{task.name}")

    async def _lose_leadership(self) -> None:
        logger.warning("background_leader_lost")
        self._state.leader = False
        await self._cancel_workers()

    async def _shutdown_workers(self) -> None:
        # Нормальная остановка: задачи видят stop-флаг и завершают текущий прогон сами.
        workers = list(self._workers.values())
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)
        self._workers.clear()
        await self._release_leadership()

    async def _release_leadership(self) -> None:
        if not self._state.leader:
            return
        self._state.leader = False
        try:
            await self._lock.release()
        except Exception:
            logger.exception("background_leader_release_failed")

    async def _cancel_workers(self) -> None:
        workers = list(self._workers.values())
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        self._workers.clear()

    async def _loop(self, task: PeriodicTask) -> None:
        if not task.run_on_start and await self._sleep(task.interval_s):
            return
        while not self._stop.is_set():
            await self._run_once(task)
            if await self._sleep(task.interval_s):
                return

    async def _run_once(self, task: PeriodicTask) -> None:
        stats = self._state.stats[task.name]
        started = time.monotonic()
        try:
            await task.run()
        except asyncio.CancelledError:
            raise
        except Exception:
            stats.failures += 1
            logger.exception("background_task_failed", task=task.name)
        finally:
            elapsed = time.monotonic() - started
            stats.runs += 1
            stats.last_duration_s = elapsed
            stats.total_duration_s += elapsed
            stats.last_run_at = time.time()

    async def _sleep(self, seconds: float) -> bool:
        """Спит до сигнала остановки; True, если остановка запрошена."""
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        except TimeoutError:
            return False
        return True
