"""Блокирующая работа в потоке, которую отмена задачи не должна бросать на полпути."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress

from hse_doc_studio.core.uow import spawn_detached


async def finish_before_cancel[**P, T](work: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    """Поток нельзя прервать: отмена дожидается его конца, иначе уборка папки разойдётся с ним и оставит хвост."""
    task = spawn_detached(asyncio.to_thread(work, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        with suppress(Exception):
            await task
        raise
