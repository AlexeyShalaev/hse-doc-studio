"""AiRelayClient: проверки раннера и запроса, постановка pinned, подбор, заголовок, поток и отмена."""

from __future__ import annotations

import asyncio
import base64
import dataclasses
from dataclasses import dataclass
from uuid import UUID

import pytest
import pytest_asyncio
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.jobs.enums import JobKind, JobState
from hse_doc_studio.core.jobs.relay import RelayErrorCode, RelayEventKind, RelayMethod, RelayPath
from hse_doc_studio.core.jobs.routing import JobRoute, PersonalRunnerSettings, RouteReason
from hse_doc_studio.core.jobs.wire import RelayEvent
from hse_doc_studio.infra.jobs.relay_hub import RelayHub
from hse_doc_studio.use_cases.ai_relay.client import (
    AiRelayClient,
    AiRelayError,
    AiRelayTimeoutError,
    RelayLimits,
    RelayRequest,
    relay_error_of,
)
from hse_doc_studio.use_cases.ai_relay.request_store import RelayRequestStore
from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService
from hse_doc_studio.use_cases.jobs.terminal import JobTerminalBroadcaster
from hse_doc_studio.use_cases.jobs.wakeup import JobWakeup

from tests.fakes.job_queue import InMemoryJobQueue
from tests.fakes.runners import InMemoryRunnerRepository
from tests.unit.use_cases.ai_relay.helpers import NOW, OWNER_ID, make_personal_runner

_ANNA = Actor.user(OWNER_ID, "Анна", "anna@example.org", is_instance_admin=True)
_BORIS = Actor.user("0b0b0b0b-0000-4000-8000-000000000000", "Борис")
_RUNNER_ID = "4f1c2b3a5d6e47f89a0b1c2d3e4f5a6b"


class _Settings:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    async def current(self) -> PersonalRunnerSettings:
        return PersonalRunnerSettings(enabled=self.enabled)


@dataclass
class _Env:
    client: AiRelayClient
    queue: InMemoryJobQueue
    runners: InMemoryRunnerRepository
    hub: RelayHub
    store: RelayRequestStore
    settings: _Settings


@pytest_asyncio.fixture
async def env() -> _Env:
    queue = InMemoryJobQueue(lambda: NOW)
    runners = InMemoryRunnerRepository()
    await runners.add(make_personal_runner(_RUNNER_ID))
    hub = RelayHub()
    terminal = JobTerminalBroadcaster()
    terminal.add(hub)
    service = JobQueueService(queue, clock=lambda: NOW, terminal=terminal)
    store = RelayRequestStore()
    settings = _Settings()
    client = AiRelayClient(
        queue,
        service,
        runners,
        hub,
        store,
        JobWakeup(),
        settings,
        limits=RelayLimits(pickup_s=0.2, max_request_bytes=1024, max_response_bytes=10, max_pending_per_user=1),
        clock=lambda: NOW,
    )
    return _Env(client, queue, runners, hub, store, settings)


def _request(**changes: object) -> RelayRequest:
    request = RelayRequest(
        runner_id=_RUNNER_ID,
        endpoint="ollama",
        path=RelayPath.chat_completions,
        method=RelayMethod.post,
        body=b'{"model":"qwen"}',
        content_type="application/json",
        stream=True,
        head_timeout_s=0.5,
        idle_timeout_s=0.5,
        project_id=None,
    )
    return dataclasses.replace(request, **changes)  # type: ignore[arg-type]


async def _only_job_id(env: _Env) -> UUID:
    for _ in range(100):
        jobs = await env.queue.list()
        if jobs:
            return jobs[0].id
        await asyncio.sleep(0.005)
    raise AssertionError("no relay job was enqueued")


def _data(raw: bytes) -> RelayEvent:
    return RelayEvent(kind=RelayEventKind.data, data=base64.b64encode(raw).decode())


async def _answer(env: _Env, *events: RelayEvent) -> UUID:
    job_id = await _only_job_id(env)
    env.hub.mark_picked(job_id)
    await env.hub.push(job_id, 0, events)
    return job_id


_HEAD = RelayEvent(kind=RelayEventKind.head, status=200, content_type="text/event-stream")
_END = RelayEvent(kind=RelayEventKind.end)


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"paused": True}, RelayErrorCode.runner_paused),
        ({"revoked_at": NOW}, RelayErrorCode.runner_revoked),
        ({"last_seen_at": None}, RelayErrorCode.runner_offline),
        ({"offline_at": NOW}, RelayErrorCode.runner_offline),
        ({"ai_endpoints": ()}, RelayErrorCode.endpoint_missing),
        ({"features": frozenset({"announce"})}, RelayErrorCode.endpoint_missing),
    ],
)
async def test__open__runner_not_ready__error_with_reason(
    env: _Env, changes: dict[str, object], code: RelayErrorCode
) -> None:
    await env.runners.add(make_personal_runner(_RUNNER_ID, **changes))

    with pytest.raises(AiRelayError) as caught:
        await env.client.open(_ANNA, _request())

    assert caught.value.code is code
    assert await env.queue.list() == ()


async def test__open__someone_elses_runner__looks_revoked(env: _Env) -> None:
    with pytest.raises(AiRelayError) as caught:
        await env.client.open(_BORIS, _request())

    assert caught.value.code is RelayErrorCode.runner_revoked
    assert caught.value.runner_name is None


async def test__open__personal_runners_disabled__disabled(env: _Env) -> None:
    env.settings.enabled = False

    with pytest.raises(AiRelayError) as caught:
        await env.client.open(_ANNA, _request())

    assert caught.value.code is RelayErrorCode.disabled
    # Отказ сразу: задача не ставится, тело не держится в памяти, человек не ждёт окна забора.
    assert not await env.queue.list()
    assert env.store.pending_for(OWNER_ID) == 0


async def test__open__body_over_the_limit__relay_too_large(env: _Env) -> None:
    with pytest.raises(AiRelayError) as caught:
        await env.client.open(_ANNA, _request(body=b"x" * 2048))

    assert caught.value.code is RelayErrorCode.relay_too_large


async def test__open__get_with_a_post_only_path__path_forbidden(env: _Env) -> None:
    with pytest.raises(AiRelayError) as caught:
        await env.client.open(_ANNA, _request(method=RelayMethod.get))

    assert caught.value.code is RelayErrorCode.path_forbidden


async def test__open__runner_does_not_pick__relay_unavailable_and_job_cancelled(env: _Env) -> None:
    with pytest.raises(AiRelayError) as caught:
        await env.client.open(_ANNA, _request())

    assert caught.value.code is RelayErrorCode.relay_unavailable
    (job,) = await env.queue.list()
    assert job.state is JobState.cancelled
    assert env.store.pending_for(OWNER_ID) == 0


async def test__open__enqueues_pinned_without_fair_share_and_without_the_body(env: _Env) -> None:
    task = asyncio.create_task(env.client.open(_ANNA, _request()))
    job_id = await _answer(env, _HEAD, _END)
    response = await task

    job = await env.queue.get(job_id)
    assert job is not None
    assert job.kind is JobKind.ai_relay
    assert job.tags == frozenset({"ai"})
    assert job.max_attempts == 1
    assert job.project_id == UUID(int=0)
    assert "qwen" not in str(job.payload)
    assert job.payload["spec"]["actor"]["email"] is None
    assert job.payload["spec"]["actor"]["is_instance_admin"] is False
    assert job.payload["spec"]["payload"]["body_size"] == len(_request().body)
    assert response.status_code == 200
    assert response.content_type == "text/event-stream"


async def test__enqueue_request__is_pinned_to_the_runner(env: _Env, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = []
    original = env.queue.enqueue

    async def spy(request):  # type: ignore[no-untyped-def]
        seen.append(request)
        return await original(request)

    monkeypatch.setattr(env.queue, "enqueue", spy)
    task = asyncio.create_task(env.client.open(_ANNA, _request()))
    await _answer(env, _HEAD, _END)
    await task

    (request,) = seen
    assert request.route is JobRoute.pinned
    assert request.target_runner_id == UUID(_RUNNER_ID)
    assert request.route_reason is RouteReason.pinned
    assert request.fair_share is False


async def test__stream__yields_chunks_then_ends_and_releases(env: _Env) -> None:
    task = asyncio.create_task(env.client.open(_ANNA, _request()))
    job_id = await _answer(env, _HEAD, _data(b"ab"), _data(b"cd"))
    response = await task
    await env.hub.push(job_id, 1, (_END,))

    chunks = [chunk async for chunk in response.aiter_bytes()]

    assert chunks == [b"ab", b"cd"]
    assert env.hub.get(job_id) is None
    assert env.store.get(job_id) is None


async def test__stream__closed_before_end__cancels_the_job(env: _Env) -> None:
    task = asyncio.create_task(env.client.open(_ANNA, _request()))
    job_id = await _answer(env, _HEAD, _data(b"ab"))
    response = await task

    await response.aclose()

    job = await env.queue.get(job_id)
    assert job is not None
    assert job.state is JobState.cancelled
    assert await env.hub.push(job_id, 1, (_data(b"x"),)) is True


async def test__stream__larger_than_the_limit__relay_too_large(env: _Env) -> None:
    task = asyncio.create_task(env.client.open(_ANNA, _request()))
    await _answer(env, _HEAD, _data(b"x" * 11))
    response = await task

    with pytest.raises(AiRelayError) as caught:
        _ = [chunk async for chunk in response.aiter_bytes()]

    assert caught.value.code is RelayErrorCode.relay_too_large


async def test__open__no_head__timeout(env: _Env) -> None:
    task = asyncio.create_task(env.client.open(_ANNA, _request(head_timeout_s=0.05)))
    job_id = await _only_job_id(env)
    env.hub.mark_picked(job_id)

    with pytest.raises(AiRelayTimeoutError):
        await task


async def test__open__runner_error_before_head__error_with_its_code(env: _Env) -> None:
    task = asyncio.create_task(env.client.open(_ANNA, _request()))
    await _answer(env, RelayEvent(kind=RelayEventKind.error, code="upstream_unreachable"))

    with pytest.raises(AiRelayError) as caught:
        await task

    assert caught.value.code is RelayErrorCode.upstream_unreachable


async def test__open__job_lost_while_waiting__relay_unavailable(env: _Env) -> None:
    task = asyncio.create_task(env.client.open(_ANNA, _request()))
    job_id = await _only_job_id(env)
    job = await env.queue.get(job_id)
    assert job is not None
    await env.hub.on_terminal(dataclasses.replace(job, state=JobState.failed, error_code="runner_lost"))

    with pytest.raises(AiRelayError) as caught:
        await task

    assert caught.value.code is RelayErrorCode.relay_unavailable


async def test__open__over_the_pending_limit__relay_busy(env: _Env) -> None:
    first = asyncio.create_task(env.client.open(_ANNA, _request()))
    await _only_job_id(env)

    with pytest.raises(AiRelayError) as caught:
        await env.client.open(_ANNA, _request())

    assert caught.value.code is RelayErrorCode.relay_busy
    with pytest.raises(AiRelayError):
        await first


def test__relay_error_of__finds_the_error_through_the_cause_chain() -> None:
    inner = AiRelayError(RelayErrorCode.relay_unavailable, runner_name="MacBook")
    outer = RuntimeError("sdk wrapped")
    outer.__cause__ = ConnectionError("transport")
    outer.__cause__.__context__ = inner

    assert relay_error_of(outer) is inner
    assert relay_error_of(ValueError("x")) is None
