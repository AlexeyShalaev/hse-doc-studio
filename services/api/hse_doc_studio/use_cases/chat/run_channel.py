"""Подписка на только что принятый запуск агента: канал шины открывает фоновая задача, а не ручка.

`POST .../turns` отвечает 202 сразу после записи запуска, а канал шины появляется при первом событии
фоновой задачи. Клиент, подписавшийся в этот промежуток, не находил канала, брал запись (ещё `running`)
и получал ложный итог `failed`, хотя ответ модели приходил через мгновение. Подписка ждёт канал или
конец записи, но не дольше предела: зависшая запись без задачи (рестарт посреди хода) отдаётся как раньше.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.agent.protocols import IAgentRunBus
from hse_doc_studio.core.enums import AgentRunStatus
from hse_doc_studio.core.repositories import IChatRepository

CHANNEL_WAIT_S = 10.0
_POLL_S = 0.05
_ACTIVE = (AgentRunStatus.pending, AgentRunStatus.running)


async def await_run_channel(
    bus: IAgentRunBus,
    chat_repo: IChatRepository,
    folder: Path,
    run_id: UUID,
    *,
    timeout_s: float = CHANNEL_WAIT_S,
) -> None:
    """Вернуться, когда у запуска есть канал шины, запись завершена или вышел предел ожидания."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while not bus.has(run_id):
        run = await chat_repo.get_run(folder, run_id)
        if run is None or run.status not in _ACTIVE or loop.time() >= deadline:
            return
        await asyncio.sleep(_POLL_S)
