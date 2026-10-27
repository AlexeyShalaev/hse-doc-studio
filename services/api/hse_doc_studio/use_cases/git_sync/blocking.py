"""Блокирующая работа в потоке, которую отмена задачи не должна бросать на полпути."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress


async def finish_before_cancel[**P, T](work: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    """Поток нельзя прервать: отмена дожидается его конца, иначе уборка папки разойдётся с ним и оставит хвост."""
    task = asyncio.ensure_future(asyncio.to_thread(work, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        with suppress(Exception):
            await task
        raise
