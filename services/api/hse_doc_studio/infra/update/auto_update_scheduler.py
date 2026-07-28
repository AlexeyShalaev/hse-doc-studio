"""Фоновый цикл автообновления (близнец idle-reaper'ов LanguageTool/Gotenberg).

Запускается один раз при старте приложения и живёт до остановки процесса. Вся
логика «надо ли и можно ли» — в `AutoUpdateUC`; здесь только расписание, чтобы
решение оставалось тестируемым без таймеров и без Docker.

Тик приходит колбэком, а не готовым use-case'ом: `AutoUpdateUC` живёт в REQUEST-скоупе
DI, и держать один экземпляр на весь процесс было бы нарушением его жизненного цикла —
каждый тик открывает свой скоуп (см. `api/entrypoint.py`).

Первый тик отложен: сразу после старта пользователь, скорее всего, что-то делает,
да и подменять контейнер, который только что подняли, — плохой первый опыт.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress

import structlog

from hse_doc_studio.use_cases.system.auto_update import AutoUpdateResult

logger = structlog.get_logger()


class AutoUpdateScheduler:
    def __init__(
        self,
        run_tick: Callable[[], Awaitable[AutoUpdateResult]],
        interval_s: float,
        startup_delay_s: float,
    ) -> None:
        self._run_tick = run_tick
        self._interval_s = interval_s
        self._startup_delay_s = startup_delay_s

    async def loop(self) -> None:
        await asyncio.sleep(self._startup_delay_s)
        while True:
            # Тик не имеет права уронить фоновую задачу: упавший цикл больше не
            # поднимется до перезапуска приложения, и обновления тихо перестанут
            # приходить. CancelledError при этом должен проходить насквозь.
            with suppress(Exception):
                result = await self._run_tick()
                logger.debug("auto-update tick", outcome=str(result.outcome), target=result.target)
            await asyncio.sleep(self._interval_s)
