"""Поток сборки сервера: строки лога и смена причины ожидания в одном потоке событий."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID

from hse_doc_studio.api.schemas.personal_runners import CompilePlacement
from hse_doc_studio.api.schemas.session import CompileWait
from hse_doc_studio.core.compile.wait import CompilePlacementInfo, CompileWaitInfo, ICompileWaitReader

_WAIT_POLL_S = 2.0
_Event = tuple[str, str]


def wait_schema(info: CompileWaitInfo | None) -> CompileWait | None:
    if info is None:
        return None
    return CompileWait(
        reason=info.reason.value,
        queue_position=info.queue_position,
        wait_hint_seconds=info.wait_hint_seconds,
        attempt=info.attempt,
        max_attempts=info.max_attempts,
    )


def placement_schema(info: CompilePlacementInfo | None) -> CompilePlacement | None:
    if info is None:
        return None
    return CompilePlacement(
        state=info.state.value,
        runner_name=info.runner_name,
        runner_owner=info.runner_owner.value if info.runner_owner is not None else None,
        fallback=info.fallback.value if info.fallback is not None else None,
        wait_s=info.wait_s,
    )


async def _pump_logs(stream: AsyncIterator[str], events: asyncio.Queue[_Event | None]) -> None:
    try:
        async for line in stream:
            await events.put(("log", line))
    finally:
        await events.put(None)


async def _pump_waits(
    waits: ICompileWaitReader, compile_id: UUID, events: asyncio.Queue[_Event | None], viewer_id: str | None
) -> None:
    """Шлёт событие только при смене причины; когда ожидание кончилось, `null` снимает его на экране.

    Тот же насос шлёт `placement`, когда меняется, где идёт сборка (ждём свой раннер, взял личный, ушла на общий).
    """
    last: str | None = None
    last_placement: str | None = None
    while True:
        info = wait_schema(await waits.of(compile_id))
        payload = "null" if info is None else info.model_dump_json()
        if payload != last and (last is not None or info is not None):
            await events.put(("wait", payload))
        last = payload
        placement = placement_schema(await waits.placement_of(compile_id, viewer_id))
        if placement is not None:
            placed = placement.model_dump_json()
            if placed != last_placement:
                await events.put(("placement", placed))
            last_placement = placed
        await asyncio.sleep(_WAIT_POLL_S)


async def merged_events(
    stream: AsyncIterator[str], waits: ICompileWaitReader, compile_id: UUID, viewer_id: str | None = None
) -> AsyncIterator[_Event]:
    """Ожидание очереди молчит в логе, а экран должен знать почему, поэтому причину присылаем отдельным событием."""
    events: asyncio.Queue[_Event | None] = asyncio.Queue()
    tasks = [asyncio.create_task(_pump_logs(stream, events))]
    if waits.enabled:
        tasks.append(asyncio.create_task(_pump_waits(waits, compile_id, events, viewer_id)))
    try:
        while (item := await events.get()) is not None:
            yield item
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
