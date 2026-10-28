"""Будильник долгого опроса: постановка задачи будит раннеры, ждущие работу в этом процессе.

Сервер один (одна реплика), поэтому достаточно памяти процесса. Пропущенный сигнал не страшен:
опрашивающий всё равно перепроверяет очередь раз в `poll_interval_s`.
"""

from __future__ import annotations

import asyncio


class JobWakeup:
    def __init__(self) -> None:
        self._waiters: set[asyncio.Future[None]] = set()

    def notify(self) -> None:
        for waiter in tuple(self._waiters):
            if not waiter.done():
                waiter.set_result(None)

    async def wait(self, timeout: float) -> None:
        """Ждёт сигнал, но не дольше `timeout` секунд."""
        if timeout <= 0:
            return
        waiter: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._waiters.add(waiter)
        try:
            await asyncio.wait_for(waiter, timeout)
        except TimeoutError:
            pass
        finally:
            self._waiters.discard(waiter)
