"""Глобальный лимит одновременных docker-сборок.

Каждая компиляция — отдельный texlive-контейнер (CPU+RAM). «Собрать всё» в
командном проекте запускает 15+ сборок разом и без ограничителя кладёт машину.
Лимитер держит не более N контейнеров одновременно; остальные сборки честно
ЖДУТ слот (не падают) — это очередь, а не отказ.

Лимит передаётся на каждый захват (читается из пользовательских настроек
`max_concurrent_compiles`), поэтому его смена в Настройках применяется к новым
сборкам сразу, без рестарта. Реализация на asyncio.Condition, а не Semaphore —
семафор не умеет менять ёмкость на лету.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class CompileConcurrencyLimiter:
    def __init__(self) -> None:
        self._active = 0
        self._cond = asyncio.Condition()

    @property
    def active(self) -> int:
        """Сколько сборок держат слот прямо сейчас (для сообщения об очереди)."""
        return self._active

    @asynccontextmanager
    async def slot(self, limit: int) -> AsyncIterator[None]:
        """Занять слот сборки; ждёт, пока активных меньше `limit`.

        Отмена во время ожидания безопасна: счётчик ещё не увеличен. Отмена
        внутри тела — слот освобождается в finally, ожидающие будятся.
        """
        capacity = max(1, limit)
        async with self._cond:
            while self._active >= capacity:
                await self._cond.wait()
            self._active += 1
        try:
            yield
        finally:
            async with self._cond:
                self._active -= 1
                self._cond.notify_all()
