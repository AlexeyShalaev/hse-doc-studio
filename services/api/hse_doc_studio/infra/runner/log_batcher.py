from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

from hse_doc_studio.core.jobs.wire import LogBatch
from hse_doc_studio.infra.runner.client import RunnerApiError, RunnerUnreachable

logger = logging.getLogger(__name__)

DEFAULT_FLUSH_S = 0.2
DEFAULT_BATCH_LINES = 200
# Потолок буфера при недоступном API: старые строки отбрасываются, сборка не копит память.
DEFAULT_BUFFER_LINES = 5000


class LogBatcher:
    """Копит строки лога задачи и отправляет порциями.

    `seq` растёт только после успешной отправки, поэтому повтор той же порции безвреден
    для сервера. Устаревшая попытка (409) гасит отправку насовсем.
    """

    def __init__(
        self,
        send: Callable[[LogBatch], Awaitable[None]],
        attempt: int,
        *,
        flush_s: float = DEFAULT_FLUSH_S,
        batch_lines: int = DEFAULT_BATCH_LINES,
        buffer_lines: int = DEFAULT_BUFFER_LINES,
    ) -> None:
        self._send = send
        self._attempt = attempt
        self._flush_s = flush_s
        self._batch_lines = batch_lines
        self._buffer_lines = buffer_lines
        self._lines: list[str] = []
        self._seq = 0
        self._dead = False
        self._full = asyncio.Event()
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None

    def append(self, line: str) -> None:
        if self._dead:
            return
        self._lines.append(line)
        if len(self._lines) > self._buffer_lines:
            del self._lines[: len(self._lines) - self._buffer_lines]
        if len(self._lines) >= self._batch_lines:
            self._full.set()

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        while True:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._full.wait(), self._flush_s)
            self._full.clear()
            await self.flush()

    async def flush(self) -> None:
        async with self._lock:
            while self._lines and not self._dead:
                chunk = self._lines[: self._batch_lines]
                try:
                    await self._send(LogBatch(attempt=self._attempt, seq=self._seq, lines=tuple(chunk)))
                except RunnerApiError as exc:
                    logger.warning("log batch rejected: %s", exc)
                    self._dead = True
                    self._lines.clear()
                    return
                except RunnerUnreachable:
                    return
                self._seq += 1
                del self._lines[: len(chunk)]

    async def close(self) -> None:
        """Останавливает фоновую отправку и сбрасывает остаток."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self.flush()
