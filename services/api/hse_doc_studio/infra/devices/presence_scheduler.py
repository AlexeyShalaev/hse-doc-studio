"""Фоновый цикл сигналов присутствия локальной Студии (близнец GitFetchScheduler).

Тик приходит колбэком: сервис живёт в REQUEST-скоупе DI, и каждый тик открывает свой скоуп (`api/entrypoint.py`).
Сколько ждать до следующего, решает сам тик: интервал называет сервер, без серверов цикл спит подолгу.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress

import structlog

from hse_doc_studio.use_cases.devices.local_presence import PresenceTick

logger = structlog.get_logger()

# После сбоя самого тика (не сети: её ловит сервис) ждём заметно дольше обычного.
FAILURE_WAIT_S = 120.0


class PresenceScheduler:
    def __init__(
        self,
        run_tick: Callable[[], Awaitable[PresenceTick]],
        *,
        startup_delay_s: float,
        wait: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._run_tick = run_tick
        self._startup_delay_s = startup_delay_s
        self._wake = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._woken_early = False
        self._wait = wait or self._wait_or_wake

    def wake(self) -> None:
        """Разбудить цикл (вход на сервер только что выполнен); можно звать из любого потока."""
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
        failing = False
        while True:
            delay = FAILURE_WAIT_S
            try:
                result = await self._run_tick()
            except Exception:
                if not failing:
                    logger.warning("presence tick failed", exc_info=True)
                failing = True
            else:
                failing = False
                delay = float(result.next_in_s)
                logger.debug("presence tick", sent=result.sent, failed=result.failed, servers=result.servers)
            await self._wait(delay)

    async def _wait_or_wake(self, seconds: float) -> None:
        with suppress(TimeoutError):
            await asyncio.wait_for(self._wake.wait(), timeout=seconds)
        self._wake.clear()
