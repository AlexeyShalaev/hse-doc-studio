"""Канал ретрансляции: порядок событий, повтор порции, пределы, обратное давление и обрыв."""

from __future__ import annotations

import asyncio
import base64
import dataclasses
from uuid import uuid4

import pytest
from hse_doc_studio.core.jobs.enums import JobState
from hse_doc_studio.core.jobs.relay import (
    RelayEventKind,
    RelayOutOfOrderError,
    RelayStreamError,
    RelayTooLargeError,
)
from hse_doc_studio.core.jobs.wire import RelayEvent
from hse_doc_studio.infra.jobs.relay_hub import RelayHub

from tests.unit.use_cases.ai_relay.helpers import make_queued_relay_job


def _head(status: int = 200) -> RelayEvent:
    return RelayEvent(kind=RelayEventKind.head, status=status, content_type="text/event-stream")


def _data(raw: bytes) -> RelayEvent:
    return RelayEvent(kind=RelayEventKind.data, data=base64.b64encode(raw).decode())


_END = RelayEvent(kind=RelayEventKind.end)


async def test__push__head_data_end__reads_in_order_and_finishes() -> None:
    hub = RelayHub()
    job_id = uuid4()
    channel = hub.open(job_id)

    assert await hub.push(job_id, 0, (_head(), _data(b"a"), _data(b"b"))) is False
    assert await hub.push(job_id, 1, (_END,)) is False

    assert await channel.wait_head(1) == (200, "text/event-stream")
    assert [await channel.read(1), await channel.read(1), await channel.read(1)] == [b"a", b"b", None]


async def test__push__repeated_seq__is_ignored() -> None:
    hub = RelayHub()
    job_id = uuid4()
    channel = hub.open(job_id)
    await hub.push(job_id, 0, (_head(), _data(b"a")))

    await hub.push(job_id, 0, (_head(), _data(b"a")))
    await hub.push(job_id, 1, (_END,))

    assert await channel.read(1) == b"a"
    assert await channel.read(1) is None


@pytest.mark.parametrize(
    ("seq", "events"),
    [
        (2, (_head(),)),
        (0, (_data(b"x"),)),
        (0, (_END,)),
        (0, (_head(), _head())),
        (0, (_head(), _END, _data(b"x"))),
    ],
    ids=["gap", "data_before_head", "end_before_head", "second_head", "after_end"],
)
async def test__push__order_violation__409(seq: int, events: tuple[RelayEvent, ...]) -> None:
    hub = RelayHub()
    job_id = uuid4()
    hub.open(job_id)

    with pytest.raises(RelayOutOfOrderError):
        await hub.push(job_id, seq, events)


async def test__push__event_over_64_kib__too_large() -> None:
    hub = RelayHub()
    job_id = uuid4()
    hub.open(job_id)

    with pytest.raises(RelayTooLargeError):
        await hub.push(job_id, 0, (_head(), _data(b"x" * (64 * 1024 + 1))))


async def test__push__batch_over_256_kib__too_large() -> None:
    hub = RelayHub()
    job_id = uuid4()
    hub.open(job_id)

    with pytest.raises(RelayTooLargeError):
        await hub.push(job_id, 0, (_head(), *(_data(b"x" * 60 * 1024) for _ in range(5))))


async def test__push__no_channel__answers_cancel() -> None:
    assert await RelayHub().push(uuid4(), 0, (_head(),)) is True


async def test__push__full_buffer__waits_for_the_consumer() -> None:
    hub = RelayHub(buffer_chunks=1)
    job_id = uuid4()
    channel = hub.open(job_id)
    await hub.push(job_id, 0, (_head(), _data(b"a")))

    second = asyncio.create_task(hub.push(job_id, 1, (_data(b"b"),)))
    await asyncio.sleep(0.01)
    assert not second.done()

    assert await channel.read(1) == b"a"
    assert await asyncio.wait_for(second, 1) is False


async def test__close__unblocks_the_runner_and_answers_cancel() -> None:
    hub = RelayHub(buffer_chunks=1)
    job_id = uuid4()
    channel = hub.open(job_id)
    await hub.push(job_id, 0, (_head(), _data(b"a")))
    blocked = asyncio.create_task(hub.push(job_id, 1, (_data(b"b"),)))
    await asyncio.sleep(0.01)

    channel.close()

    assert await asyncio.wait_for(blocked, 1) is True
    assert channel.consumer_closed


async def test__push__consumer_closed_after_end__repeated_batch_is_not_cancelled() -> None:
    hub = RelayHub()
    job_id = uuid4()
    channel = hub.open(job_id)
    await hub.push(job_id, 0, (_head(), _data(b"a"), _END))
    assert [await channel.read(1), await channel.read(1)] == [b"a", None]

    channel.close()

    assert await hub.push(job_id, 0, (_head(), _data(b"a"), _END)) is False


async def test__error_event__breaks_the_stream_with_its_code() -> None:
    hub = RelayHub()
    job_id = uuid4()
    channel = hub.open(job_id)
    await hub.push(job_id, 0, (_head(), _data(b"a")))

    await hub.push(job_id, 1, (RelayEvent(kind=RelayEventKind.error, code="upstream_timeout"),))

    assert await channel.read(1) == b"a"
    with pytest.raises(RelayStreamError) as caught:
        await channel.read(1)
    assert caught.value.code == "upstream_timeout"


async def test__on_terminal__before_head__head_fails_with_relay_unavailable() -> None:
    hub = RelayHub()
    job = make_queued_relay_job(state=JobState.failed, error_code="runner_lost")
    channel = hub.open(job.id)

    await hub.on_terminal(job)

    assert await channel.wait_picked(0.01)
    with pytest.raises(RelayStreamError) as caught:
        await channel.wait_head(1)
    assert caught.value.code == "relay_unavailable"


async def test__on_terminal__after_end__changes_nothing() -> None:
    hub = RelayHub()
    job = make_queued_relay_job(state=JobState.succeeded)
    channel = hub.open(job.id)
    await hub.push(job.id, 0, (_head(), _data(b"a"), _END))

    await hub.on_terminal(dataclasses.replace(job, error_code="cancelled"))

    assert await channel.read(1) == b"a"
    assert await channel.read(1) is None


async def test__read__silence__times_out() -> None:
    hub = RelayHub()
    job_id = uuid4()
    channel = hub.open(job_id)
    await hub.push(job_id, 0, (_head(),))

    with pytest.raises(TimeoutError):
        await channel.read(0.01)
