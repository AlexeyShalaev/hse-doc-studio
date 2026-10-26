"""Фоновый цикл выборки из удалённых репозиториев (близнец AutoUpdateScheduler).

Тик приходит колбэком: use case живёт в REQUEST-скоупе DI, и каждый тик открывает свой скоуп
(см. `api/entrypoint.py`). Решение «чей черёд» принимает сам use case, здесь только расписание.

Пока ни один проект не подключён к репозиторию, цикл спит подолгу и ничего не запускает; подключение
или клонирование будит его сразу (`wake`), поэтому первая выборка нового проекта не ждёт конца сна.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress

import structlog

from hse_doc_studio.use_cases.git_sync.fetch_all_remotes import FetchTickResult

logger = structlog.get_logger()

IDLE_SLEEP_S = 600.0


class GitFetchScheduler:
    def __init__(
        self,
        run_tick: Callable[[], Awaitable[FetchTickResult]],
        *,
        tick_s: float,
        startup_delay_s: float,
        idle_s: float = IDLE_SLEEP_S,
        wait: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._run_tick = run_tick
        self._tick_s = tick_s
        self._startup_delay_s = startup_delay_s
        self._idle_s = idle_s
        self._wake = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._woken_early = False
        # Подмена ожидания нужна тестам: настоящее ждёт сигнала или срока.
        self._wait = wait or self._wait_or_wake

    def wake(self) -> None:
        """Разбудить цикл; можно звать из любого потока."""
        loop = self._loop
        if loop is None:
            self._woken_early = True
            return
        with suppress(RuntimeError):
            loop.call_soon_threadsafe(self._wake.set)

    async def loop(self) -> None:
        self._loop = asyncio.get_running_loop()
        if self._woken_early:
            self._wake.set()
        await self._wait(self._startup_delay_s)
        while True:
            delay = self._tick_s
            # Тик не имеет права уронить фоновую задачу: упавший цикл не поднимется до перезапуска, и выборка
            # тихо перестанет работать. CancelledError при этом должен проходить насквозь.
            with suppress(Exception):
                result = await self._run_tick()
                logger.debug(
                    "git fetch tick",
                    registered=result.registered,
                    fetched=result.fetched,
                    failed=result.failed,
                )
                if result.registered == 0:
                    delay = self._idle_s
            await self._wait(delay)

    async def _wait_or_wake(self, seconds: float) -> None:
        with suppress(TimeoutError):
            await asyncio.wait_for(self._wake.wait(), timeout=seconds)
        self._wake.clear()
