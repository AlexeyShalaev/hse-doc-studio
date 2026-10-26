from __future__ import annotations

import asyncio
from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.agent.entities import AgentEvent
from hse_doc_studio.core.enums import AgentEventType
from hse_doc_studio.core.events import IEventBus
from hse_doc_studio.infra.ai.agent.run_bus import AgentRunBus
from hse_doc_studio.infra.compile.log_bus import CompileLogBus

# (bus factory, event factory) for every in-memory implementation of IEventBus.
_BUSES: list[tuple[Callable[[], IEventBus], Callable[[int], object]]] = [
    (CompileLogBus, lambda n: f"line-{n}"),
    (AgentRunBus, lambda n: AgentEvent(type=AgentEventType.token, data={"n": n})),
]
_IDS = ["compile_log_bus", "agent_run_bus"]


async def _collect(bus: IEventBus, topic: UUID) -> list[object]:
    return [event async for event in bus.subscribe(topic)]


@pytest.mark.unit
@pytest.mark.parametrize(("make_bus", "make_event"), _BUSES, ids=_IDS)
async def test__event_bus__late_subscriber__gets_full_replay_then_live(make_bus, make_event) -> None:
    bus = make_bus()
    topic = uuid4()
    bus.publish(topic, make_event(0))
    bus.publish(topic, make_event(1))

    received: list[object] = []

    async def consume() -> None:
        async for event in bus.subscribe(topic):
            received.append(event)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.02)
    assert received == [make_event(0), make_event(1)]

    bus.publish(topic, make_event(2))
    bus.close(topic)
    await asyncio.wait_for(task, timeout=1)
    assert received == [make_event(0), make_event(1), make_event(2)]


@pytest.mark.unit
@pytest.mark.parametrize(("make_bus", "make_event"), _BUSES, ids=_IDS)
async def test__event_bus__close__ends_all_subscribers(make_bus, make_event) -> None:
    bus = make_bus()
    topic = uuid4()
    tasks = [asyncio.create_task(_collect(bus, topic)) for _ in range(2)]
    await asyncio.sleep(0.02)
    assert not any(t.done() for t in tasks)

    bus.close(topic)

    assert await asyncio.wait_for(asyncio.gather(*tasks), timeout=1) == [[], []]


@pytest.mark.unit
@pytest.mark.parametrize(("make_bus", "make_event"), _BUSES, ids=_IDS)
async def test__event_bus__publish_after_close__is_ignored(make_bus, make_event) -> None:
    bus = make_bus()
    topic = uuid4()
    bus.publish(topic, make_event(0))
    bus.close(topic)
    bus.publish(topic, make_event(1))

    assert await _collect(bus, topic) == [make_event(0)]


@pytest.mark.unit
@pytest.mark.parametrize(("make_bus", "make_event"), _BUSES, ids=_IDS)
async def test__event_bus__close_twice__is_idempotent(make_bus, make_event) -> None:
    bus = make_bus()
    topic = uuid4()
    bus.publish(topic, make_event(0))
    bus.close(topic)
    bus.close(topic)

    assert await _collect(bus, topic) == [make_event(0)]


@pytest.mark.unit
@pytest.mark.parametrize(("make_bus", "make_event"), _BUSES, ids=_IDS)
async def test__event_bus__discard__drops_history(make_bus, make_event) -> None:
    bus = make_bus()
    topic = uuid4()
    bus.publish(topic, make_event(0))
    bus.close(topic)
    assert bus.has(topic)

    bus.discard(topic)

    assert not bus.has(topic)
    bus.close(topic)  # a fresh channel: nothing is replayed from the discarded one
    assert await _collect(bus, topic) == []


@pytest.mark.unit
@pytest.mark.parametrize(("make_bus", "make_event"), _BUSES, ids=_IDS)
def test__event_bus__has__false_for_unknown_topic(make_bus, make_event) -> None:
    bus = make_bus()

    assert not bus.has(uuid4())
    bus.discard(uuid4())  # discarding an unknown topic is a no-op


@pytest.mark.unit
@pytest.mark.parametrize(("make_bus", "make_event"), _BUSES, ids=_IDS)
async def test__event_bus__two_subscribers__see_same_sequence(make_bus, make_event) -> None:
    bus = make_bus()
    topic = uuid4()
    bus.publish(topic, make_event(0))
    first = asyncio.create_task(_collect(bus, topic))
    await asyncio.sleep(0.02)
    bus.publish(topic, make_event(1))
    second = asyncio.create_task(_collect(bus, topic))
    await asyncio.sleep(0.02)
    bus.publish(topic, make_event(2))
    bus.close(topic)

    a, b = await asyncio.wait_for(asyncio.gather(first, second), timeout=1)
    assert a == b == [make_event(0), make_event(1), make_event(2)]
