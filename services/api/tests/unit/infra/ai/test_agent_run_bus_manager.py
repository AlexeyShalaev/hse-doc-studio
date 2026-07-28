from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.agent.entities import AgentEvent
from hse_doc_studio.core.enums import AgentEventType
from hse_doc_studio.infra.ai.agent.run_bus import AgentRunBus
from hse_doc_studio.infra.ai.agent.run_manager import AgentRunManager


@pytest.mark.unit
async def test__run_bus__replays_buffered_then_closes() -> None:
    bus = AgentRunBus()
    rid = uuid4()
    bus.publish(rid, AgentEvent(type=AgentEventType.token, data={"text": "a"}))
    bus.publish(rid, AgentEvent(type=AgentEventType.token, data={"text": "b"}))
    bus.close(rid)

    received = [e.data["text"] async for e in bus.subscribe(rid)]
    assert received == ["a", "b"]


@pytest.mark.unit
async def test__run_bus__delivers_live_events_then_exits_on_close() -> None:
    bus = AgentRunBus()
    rid = uuid4()
    received: list[int] = []

    async def consume() -> None:
        async for event in bus.subscribe(rid):
            received.append(event.data["n"])

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.02)  # let the consumer reach the wait
    bus.publish(rid, AgentEvent(type=AgentEventType.iteration, data={"n": 1}))
    await asyncio.sleep(0.02)
    bus.close(rid)
    await asyncio.wait_for(task, timeout=1.0)

    assert received == [1]


async def _register_running(manager: AgentRunManager, session_id: UUID, run_id: UUID) -> asyncio.Task[None]:
    started = asyncio.Event()

    async def long_run() -> None:
        started.set()
        await asyncio.sleep(10)

    task = asyncio.create_task(long_run())
    manager.register(run_id, task, session_id, Path("."))
    await asyncio.wait_for(started.wait(), timeout=1.0)
    return task


@pytest.mark.unit
async def test__run_manager__register__is_tracked_as_active() -> None:
    manager = AgentRunManager()
    session_id = uuid4()
    run_id = uuid4()
    task = await _register_running(manager, session_id, run_id)

    assert manager.is_running(run_id) is True
    assert manager.active_run_for_session(session_id) == run_id

    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


@pytest.mark.unit
async def test__run_manager__cancel__stops_tracking_run() -> None:
    manager = AgentRunManager()
    session_id = uuid4()
    run_id = uuid4()
    task = await _register_running(manager, session_id, run_id)

    assert await manager.cancel(run_id) is True

    with suppress(asyncio.CancelledError):
        await task
    assert manager.is_running(run_id) is False
    assert manager.active_run_for_session(session_id) is None


@pytest.mark.unit
async def test__run_manager__session_lock_is_stable_per_session() -> None:
    manager = AgentRunManager()
    sid = uuid4()
    assert manager.session_lock(sid) is manager.session_lock(sid)
    assert await manager.cancel(uuid4()) is False  # unknown run → False, no raise
