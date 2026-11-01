"""Ретрансляция ИИ поверх настоящих маршрутов раннера: тело запроса, порции ответа, отмена и чужой токен."""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.guards import install_exception_handlers
from hse_doc_studio.api.routers.server_routers import include_server_routers
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.jobs.enums import JobState
from hse_doc_studio.core.jobs.relay import RelayErrorCode, RelayMethod, RelayPath
from hse_doc_studio.core.jobs.runners import RunnerOwnerKind
from hse_doc_studio.core.jobs.wire import RUNNER_PROTOCOL_VERSION, SERVER_FEATURES
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.jobs.relay_hub import RelayHub
from hse_doc_studio.infra.jobs.storage_fs import FsJobBlobStore, FsJobLogSink, FsJobOutputIngest
from hse_doc_studio.use_cases.ai_relay.client import AiRelayClient, AiRelayError, RelayLimits, RelayRequest
from hse_doc_studio.use_cases.ai_relay.request_store import RelayRequestStore
from hse_doc_studio.use_cases.ai_relay.runner_side import RelayRunnerService
from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService
from hse_doc_studio.use_cases.jobs.runner_io import RunnerJobIoService
from hse_doc_studio.use_cases.jobs.runner_jobs import RunnerJobService
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry
from hse_doc_studio.use_cases.jobs.terminal import JobTerminalBroadcaster
from hse_doc_studio.use_cases.jobs.wakeup import JobWakeup
from httpx import ASGITransport, AsyncClient

from tests.fakes.auth import InMemoryAuditLog
from tests.fakes.job_queue import InMemoryJobQueue
from tests.fakes.runners import InMemoryRegistrationTokenRepository, InMemoryRunnerRepository
from tests.unit.use_cases.ai_relay.helpers import OWNER_ID, make_personal_runner

_ADMIN = Actor(kind="user", id="admin", is_instance_admin=True)
_ANNA = Actor.user(OWNER_ID, "Анна")
_BODY = b'{"model":"qwen","stream":true}'


class _Uow:
    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        yield


@dataclass
class _Leased:
    headers: dict[str, str]
    job_id: UUID
    job_token: str

    @property
    def auth(self) -> dict[str, str]:
        return {**self.headers, "X-Job-Token": self.job_token}


@dataclass
class _Env:
    client: AsyncClient
    queue: InMemoryJobQueue
    runners: InMemoryRunnerRepository
    registry: RunnerRegistry
    relay: AiRelayClient

    async def register(self, *, owner: str = OWNER_ID) -> tuple[dict[str, str], str]:
        created = await self.registry.create_registration_token(_ADMIN)
        response = await self.client.post(
            "/api/runner/v1/register",
            json={
                "name": "MacBook",
                "protocol": RUNNER_PROTOCOL_VERSION,
                "version": "0.3.0",
                "tags": ["ai", "pack"],
                "concurrency": 1,
                "resource_class": "standard",
            },
            headers={"Authorization": f"Bearer {created.secret}"},
        )
        body = response.json()
        runner = await self.runners.get(body["runner_id"])
        assert runner is not None
        # Владелец и объявленные адреса появятся с личными токенами и /announce; здесь их ставит тест.
        personal = make_personal_runner(runner.id, owner_id=owner, last_seen_at=datetime.now(UTC))
        await self.runners.add(dataclasses.replace(personal, token_hash=runner.token_hash))
        return {"Authorization": f"Bearer {body['runner_token']}"}, runner.id

    async def lease(self, headers: dict[str, str]) -> _Leased:
        for _ in range(100):
            polled = await self.client.post(
                "/api/runner/v1/poll", json={"wait_s": 0, "free_slots": 0, "free_ai_slots": 1}, headers=headers
            )
            envelope = polled.json()["envelope"]
            if envelope is not None:
                return _Leased(headers, UUID(envelope["spec"]["id"]), envelope["job_token"])
            await asyncio.sleep(0.01)
        raise AssertionError("relay job was not handed out")

    def url(self, leased: _Leased, tail: str) -> str:
        return f"/api/runner/v1/jobs/{leased.job_id}/relay/{tail}"


def _request(runner_id: str) -> RelayRequest:
    return RelayRequest(
        runner_id=runner_id,
        endpoint="ollama",
        path=RelayPath.chat_completions,
        method=RelayMethod.post,
        body=_BODY,
        content_type="application/json",
        stream=True,
        head_timeout_s=2.0,
        idle_timeout_s=2.0,
        project_id=None,
    )


def _events(seq: int, *events: dict[str, object]) -> dict[str, object]:
    full = [{"kind": "data", "status": None, "content_type": None, "data": None, "code": None} | e for e in events]
    return {"attempt": 1, "seq": seq, "events": full}


_HEAD = {"kind": "head", "status": 200, "content_type": "text/event-stream"}
_END = {"kind": "end"}


def _data(raw: bytes) -> dict[str, object]:
    return {"kind": "data", "data": base64.b64encode(raw).decode()}


@pytest_asyncio.fixture
async def env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> AsyncIterator[_Env]:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    queue = InMemoryJobQueue()
    runners = InMemoryRunnerRepository()
    registry = RunnerRegistry(runners, InMemoryRegistrationTokenRepository(), InMemoryAuditLog(), _Uow())
    from hse_doc_studio.core.jobs.runners import JobTokenSigner  # noqa: PLC0415

    signer = JobTokenSigner([b"k" * 32])
    hub = RelayHub()
    terminal = JobTerminalBroadcaster()
    terminal.add(hub)
    wakeup = JobWakeup()
    queue_service = JobQueueService(queue, terminal=terminal, wakeup=wakeup)
    poll = RunnerJobService(queue, queue_service, runners, signer, wakeup, lease_s=45.0, timeout_grace_s=15.0)
    io = RunnerJobIoService(
        queue,
        queue_service,
        runners,
        signer,
        FsJobBlobStore(tmp_path),
        FsJobOutputIngest(tmp_path, max_bytes=1000),
        FsJobLogSink(tmp_path, max_bytes=1000),
    )
    store = RelayRequestStore()
    relay = AiRelayClient(queue, queue_service, runners, hub, store, wakeup, limits=RelayLimits(pickup_s=2.0))
    side = RelayRunnerService(io, store, hub)

    class _Provider(Provider):
        scope = Scope.APP

        @provide
        def registry_(self) -> RunnerRegistry:
            return registry

        @provide
        def poll_(self) -> RunnerJobService:
            return poll

        @provide
        def io_(self) -> RunnerJobIoService:
            return io

        @provide
        def side_(self) -> RelayRunnerService:
            return side

    app = FastAPI()
    include_server_routers(app)
    install_exception_handlers(app)
    container = make_async_container(_Provider(), FastapiProvider())
    setup_dishka(container, app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield _Env(client, queue, runners, registry, relay)
    await container.close()


async def test__relay__body_then_events__stream_reaches_the_consumer(env: _Env) -> None:
    headers, runner_id = await env.register()
    opening = asyncio.create_task(env.relay.open(_ANNA, _request(runner_id)))
    leased = await env.lease(headers)

    body = await env.client.get(env.url(leased, "request"), headers=leased.auth)
    assert body.status_code == 200
    assert body.content == _BODY
    assert body.headers["X-Relay-Sha256"] == hashlib.sha256(_BODY).hexdigest()
    first = await env.client.post(
        env.url(leased, "events"), json=_events(0, _HEAD, _data(b"tok1")), headers=leased.auth
    )
    assert first.json() == {"cancel": False}
    response = await opening
    await env.client.post(env.url(leased, "events"), json=_events(1, _data(b"tok2"), _END), headers=leased.auth)

    assert response.status_code == 200
    assert [chunk async for chunk in response.aiter_bytes()] == [b"tok1", b"tok2"]


async def test__relay__consumer_closed__next_ack_cancels(env: _Env) -> None:
    headers, runner_id = await env.register()
    opening = asyncio.create_task(env.relay.open(_ANNA, _request(runner_id)))
    leased = await env.lease(headers)
    await env.client.get(env.url(leased, "request"), headers=leased.auth)
    await env.client.post(env.url(leased, "events"), json=_events(0, _HEAD), headers=leased.auth)
    response = await opening

    await response.aclose()
    ack = await env.client.post(env.url(leased, "events"), json=_events(1, _data(b"x")), headers=leased.auth)
    beat = await env.client.post(
        f"/api/runner/v1/jobs/{leased.job_id}/heartbeat", json={"attempt": 1}, headers=leased.auth
    )

    assert ack.json() == {"cancel": True}
    assert beat.json()["cancel"] is True


async def test__relay__gap_in_seq__409_out_of_order(env: _Env) -> None:
    headers, runner_id = await env.register()
    opening = asyncio.create_task(env.relay.open(_ANNA, _request(runner_id)))
    leased = await env.lease(headers)
    await env.client.get(env.url(leased, "request"), headers=leased.auth)

    response = await env.client.post(env.url(leased, "events"), json=_events(3, _HEAD), headers=leased.auth)

    assert response.status_code == 409
    assert response.json()["code"] == "relay_out_of_order"
    opening.cancel()


async def test__relay__event_over_64_kib__413(env: _Env) -> None:
    headers, runner_id = await env.register()
    opening = asyncio.create_task(env.relay.open(_ANNA, _request(runner_id)))
    leased = await env.lease(headers)

    response = await env.client.post(
        env.url(leased, "events"), json=_events(0, _HEAD, _data(b"x" * (64 * 1024 + 1))), headers=leased.auth
    )

    assert response.status_code == 413
    assert response.json()["code"] == "relay_too_large"
    opening.cancel()


async def test__relay__another_runners_token__401(env: _Env) -> None:
    headers, runner_id = await env.register()
    other_headers, _ = await env.register()
    opening = asyncio.create_task(env.relay.open(_ANNA, _request(runner_id)))
    leased = await env.lease(headers)

    stolen = {**other_headers, "X-Job-Token": leased.job_token}
    body = await env.client.get(env.url(leased, "request"), headers=stolen)
    events = await env.client.post(env.url(leased, "events"), json=_events(0, _HEAD), headers=stolen)

    assert body.status_code == 401
    assert events.status_code == 401
    opening.cancel()


async def test__relay__request_after_consumer_left__404_gone(env: _Env) -> None:
    headers, runner_id = await env.register()
    opening = asyncio.create_task(env.relay.open(_ANNA, _request(runner_id)))
    leased = await env.lease(headers)
    opening.cancel()
    with pytest.raises(asyncio.CancelledError):
        await opening

    response = await env.client.get(env.url(leased, "request"), headers=leased.auth)

    assert response.status_code in (404, 409)
    job = await env.queue.get(leased.job_id)
    assert job is not None
    assert job.cancel_requested or job.state is JobState.cancelled


async def test__relay__runner_lost__consumer_gets_relay_unavailable(env: _Env) -> None:
    headers, runner_id = await env.register()
    opening = asyncio.create_task(env.relay.open(_ANNA, _request(runner_id)))
    leased = await env.lease(headers)
    await env.client.get(env.url(leased, "request"), headers=leased.auth)

    await env.client.post(
        f"/api/runner/v1/jobs/{leased.job_id}/complete",
        json={
            "attempt": 1,
            "result": {
                "status": "failed",
                "data": None,
                "error": {"category": "unavailable", "code": "upstream_unreachable", "detail": ""},
            },
            "artifacts": [],
        },
        headers=leased.auth,
    )

    with pytest.raises(AiRelayError) as caught:
        await opening
    assert caught.value.code is RelayErrorCode.upstream_unreachable


async def test__relay__runner_of_someone_else__refused_before_queueing(env: _Env) -> None:
    _, runner_id = await env.register(owner="0b0b0b0b-0000-4000-8000-000000000000")

    with pytest.raises(AiRelayError) as caught:
        await env.relay.open(_ANNA, _request(runner_id))

    assert caught.value.code is RelayErrorCode.runner_revoked
    assert await env.queue.list() == ()
    assert (await env.runners.get(runner_id)).owner_kind is RunnerOwnerKind.user  # type: ignore[union-attr]
    assert SERVER_FEATURES
