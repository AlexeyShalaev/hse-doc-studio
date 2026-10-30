"""Рассылка терминального состояния задачи очереди тем, кто держит по ней живое состояние в памяти api."""

from __future__ import annotations

import structlog

from hse_doc_studio.core.jobs.protocols import IJobTerminalListener
from hse_doc_studio.core.jobs.queue import QueuedJob

logger = structlog.get_logger(__name__)


class JobTerminalBroadcaster:
    """Слушатели регистрируются при сборке контейнера; рассылка идёт по порядку регистрации."""

    def __init__(self) -> None:
        self._listeners: list[IJobTerminalListener] = []

    def add(self, listener: IJobTerminalListener) -> None:
        self._listeners.append(listener)

    async def emit(self, job: QueuedJob) -> None:
        """Зовёт всех слушателей; исключение одного логируется и не мешает остальным."""
        if not job.state.is_terminal:
            return
        for listener in tuple(self._listeners):
            try:
                await listener.on_terminal(job)
            except Exception:
                logger.exception("job_terminal_listener_failed", job_id=str(job.id))
