"""Остановка процесса: сигнал пришёл, ожидающим запросам пора отвечать, а не ждать отмены сервером.

uvicorn по SIGTERM перестаёт принимать соединения и ждёт идущие запросы `timeout_graceful_shutdown` секунд, а
потом отменяет их, и клиент получает голый 500. Флаг поднимается в момент сигнала: долгие ожидания (MCP
`compile_document`, потоки событий) завершаются сразу понятным ответом, и окно выкатки короче.
"""

from __future__ import annotations

import asyncio

# Через сколько секунд повторять: старт нового пода api с проверками готовности занимает 10–20 с.
RESTART_RETRY_AFTER_S = 30


class ServerRestartingError(Exception):
    """Сервер останавливается (выкатка, перезапуск): ответа в этом запросе не будет, повторить позже."""

    def __init__(self, message: str, *, retry_after_s: int = RESTART_RETRY_AFTER_S) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class ShutdownSignal:
    """Флаг остановки процесса и ожидание его в корутинах.

    `request()` вызывается из обработчика сигнала в главном потоке, то есть посреди цикла событий: само событие
    поднимается через `call_soon_threadsafe`, а не прямо из обработчика.
    """

    def __init__(self) -> None:
        self._requested = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._event: asyncio.Event | None = None

    @property
    def requested(self) -> bool:
        return self._requested

    def request(self) -> None:
        if self._requested:
            return
        self._requested = True
        loop, event = self._loop, self._event
        if loop is not None and event is not None and not loop.is_closed():
            loop.call_soon_threadsafe(event.set)

    async def wait(self) -> None:
        event = self._event_for_running_loop()
        if self._requested:
            return
        await event.wait()

    async def wait_for(self, timeout_s: float) -> bool:
        """Ждёт остановку не дольше `timeout_s`; True, если она началась."""
        try:
            async with asyncio.timeout(timeout_s):
                await self.wait()
        except TimeoutError:
            return False
        return True

    def reset(self) -> None:
        """Для тестов: процесс снова «живой»."""
        self._requested = False
        self._loop = None
        self._event = None

    def _event_for_running_loop(self) -> asyncio.Event:
        loop = asyncio.get_running_loop()
        if self._event is None or self._loop is not loop:
            # Событие привязано к циклу: в тестах цикл у каждого теста свой.
            self._loop, self._event = loop, asyncio.Event()
            if self._requested:
                self._event.set()
        return self._event


_PROCESS_SHUTDOWN = ShutdownSignal()


def process_shutdown() -> ShutdownSignal:
    """Флаг остановки этого процесса: один на процесс, как и сигнал."""
    return _PROCESS_SHUTDOWN


__all__ = [
    "RESTART_RETRY_AFTER_S",
    "ServerRestartingError",
    "ShutdownSignal",
    "process_shutdown",
]
