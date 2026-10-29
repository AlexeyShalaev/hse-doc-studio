"""Опрос и heartbeat раннера поверх настоящих маршрутов: очередь в памяти, часы подставляются."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.guards import install_exception_handlers
from hse_doc_studio.api.routers.server_routers import include_server_routers
from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.jobs.codec import encode_envelope
from hse_doc_studio.core.jobs.entities import JobSpec
from hse_doc_studio.core.jobs.enums import JobKind, JobState
from hse_doc_studio.core.jobs.files import ManifestFile
from hse_doc_studio.core.jobs.queue import EnqueueRequest
from hse_doc_studio.core.jobs.runners import JobTokenSigner
from hse_doc_studio.core.jobs.wire import RUNNER_PROTOCOL_VERSION, JobEnvelope
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService
from hse_doc_studio.use_cases.jobs.runner_jobs import RunnerJobService
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry
from hse_doc_studio.use_cases.jobs.wakeup import JobWakeup
from httpx import ASGITransport, AsyncClient

from tests.fakes.auth import InMemoryAuditLog
from tests.fakes.job_queue import InMemoryJobQueue
from tests.fakes.runners import InMemoryRegistrationTokenRepository, InMemoryRunnerRepository
from tests.unit.core.jobs.samples import make_compile_spec

_ADMIN = Actor(kind="user", id="admin", is_instance_admin=True)


class _Uow:
    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        yield


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@dataclass
class _Env:
    client: AsyncClient
    queue: InMemoryJobQueue
    wakeup: JobWakeup
    clock: _Clock
    registry: RunnerRegistry

    async def register(self) -> dict[str, str]:
        created = await self.registry.create_registration_token(_ADMIN)
        response = await self.client.post(
            "/api/runner/v1/register",
            json={
                "name": "r",
                "protocol": RUNNER_PROTOCOL_VERSION,
                "version": "1",
                "tags": ["compile"],
                "concurrency": 1,
                "resource_class": "standard",
            },
            headers={"Authorization": f"Bearer {created.secret}"},
        )
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['runner_token']}"}

    async def enqueue(self, spec: JobSpec | None = None) -> UUID:
        spec = spec or make_compile_spec()
        job_id = uuid4()
        envelope = JobEnvelope(
            spec=spec,
            manifest=(ManifestFile("main.tex", "a" * 64, 3),),
            timeout_s=600.0,
            attempt=1,
            job_token="placeholder",
            actor_role=Role.editor,
        )
        payload = {k: v for k, v in encode_envelope(envelope).items() if k not in {"job_token", "attempt"}}
        await self.queue.enqueue(
            EnqueueRequest(
                job_id=job_id,
                kind=JobKind.compile,
                project_id=uuid4(),
                user_id=uuid4(),
                tags=frozenset({"compile"}),
                payload=payload,
                max_attempts=2,
                timeout_s=600.0,
            )
        )
        self.wakeup.notify()
        return job_id


@pytest_asyncio.fixture
async def env(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Env]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    clock = _Clock()
    queue = InMemoryJobQueue(clock)
    runners = InMemoryRunnerRepository()
    registry = RunnerRegistry(runners, InMemoryRegistrationTokenRepository(), InMemoryAuditLog(), _Uow())
    wakeup = JobWakeup()
    service = RunnerJobService(
        queue,
        JobQueueService(queue, lease_s=45.0, timeout_grace_s=15.0, clock=clock),
        runners,
        JobTokenSigner([b"k" * 32]),
        wakeup,
        lease_s=45.0,
        timeout_grace_s=15.0,
        poll_interval_s=0.05,
        clock=clock,
    )

    class _Provider(Provider):
        scope = Scope.APP

        @provide
        def registry_(self) -> RunnerRegistry:
            return registry

        @provide
        def service_(self) -> RunnerJobService:
            return service

    app = FastAPI()
    include_server_routers(app)
    install_exception_handlers(app)
    container = make_async_container(_Provider(), FastapiProvider())
    setup_dishka(container, app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield _Env(client, queue, wakeup, clock, registry)
    await container.close()


async def _poll(env: _Env, headers: dict[str, str], wait_s: int = 0) -> dict[str, object]:
    response = await env.client.post("/api/runner/v1/poll", json={"wait_s": wait_s, "free_slots": 1}, headers=headers)
    assert response.status_code == 200
    return dict(response.json())


async def test__poll__empty_queue_and_no_wait__returns_null_envelope(env: _Env) -> None:
    headers = await env.register()

    assert await _poll(env, headers) == {"envelope": None}


async def test__poll__queued_job__returns_envelope_with_token_and_attempt(env: _Env) -> None:
    headers = await env.register()
    job_id = await env.enqueue()

    data = await _poll(env, headers)

    envelope = data["envelope"]
    assert isinstance(envelope, dict)
    assert envelope["attempt"] == 1
    assert envelope["job_token"]
    assert envelope["actor_role"] == "editor"
    job = await env.queue.get(job_id)
    assert job is not None
    assert job.state is JobState.running


async def test__poll__waiting_runner_gets_job_right_after_enqueue(env: _Env) -> None:
    headers = await env.register()
    waiting = asyncio.create_task(_poll(env, headers, wait_s=10))
    await asyncio.sleep(0.1)
    started = time.monotonic()

    await env.enqueue()
    data = await asyncio.wait_for(waiting, 3)

    assert data["envelope"] is not None
    assert time.monotonic() - started < 2


async def test__poll__nothing_arrives__answers_empty_after_wait(env: _Env) -> None:
    headers = await env.register()
    started = time.monotonic()

    data = await _poll(env, headers, wait_s=1)

    assert data == {"envelope": None}
    assert 0.9 <= time.monotonic() - started < 3


async def test__poll__paused_runner__gets_nothing(env: _Env) -> None:
    headers = await env.register()
    runner = (await env.registry.list_runners(_ADMIN))[0]
    await env.registry.set_paused(_ADMIN, runner.id, True)
    await env.enqueue()

    assert await _poll(env, headers) == {"envelope": None}


async def test__poll__bad_token_or_wait_out_of_range__rejected(env: _Env) -> None:
    bad = await env.client.post(
        "/api/runner/v1/poll", json={"wait_s": 0, "free_slots": 1}, headers={"Authorization": "Bearer hsrn_nope"}
    )
    assert bad.status_code == 401
    assert bad.json()["code"] == "runner_unauthorized"
    headers = await env.register()
    too_long = await env.client.post("/api/runner/v1/poll", json={"wait_s": 26, "free_slots": 1}, headers=headers)
    assert too_long.status_code == 422


async def _leased(env: _Env) -> tuple[dict[str, str], UUID, dict[str, object]]:
    headers = await env.register()
    job_id = await env.enqueue()
    envelope = (await _poll(env, headers))["envelope"]
    assert isinstance(envelope, dict)
    return headers, job_id, envelope


def _beat(env: _Env, headers: dict[str, str], job_id: UUID, envelope: dict[str, object], attempt: int = 1):  # type: ignore[no-untyped-def]
    return env.client.post(
        f"/api/runner/v1/jobs/{job_id}/heartbeat",
        json={"attempt": attempt},
        headers={**headers, "X-Job-Token": str(envelope["job_token"])},
    )


async def test__heartbeat__extends_lease_without_cancel(env: _Env) -> None:
    headers, job_id, envelope = await _leased(env)
    env.clock.advance(10)

    response = await _beat(env, headers, job_id, envelope)

    assert response.status_code == 200
    assert response.json()["cancel"] is False
    job = await env.queue.get(job_id)
    assert job is not None
    assert job.lease_until == env.clock.now + timedelta(seconds=45)


async def test__heartbeat__cancel_requested__delivers_cancel(env: _Env) -> None:
    headers, job_id, envelope = await _leased(env)
    await env.queue.request_cancel(job_id)

    response = await _beat(env, headers, job_id, envelope)

    assert response.status_code == 200
    assert response.json()["cancel"] is True


async def test__heartbeat__overdue_job__delivers_cancel(env: _Env) -> None:
    headers, job_id, envelope = await _leased(env)
    env.clock.advance(601)

    assert (await _beat(env, headers, job_id, envelope)).json()["cancel"] is True


async def test__heartbeat__stale_attempt__409(env: _Env) -> None:
    headers, job_id, envelope = await _leased(env)

    response = await _beat(env, headers, job_id, envelope, attempt=2)

    assert response.status_code == 409
    assert response.json()["code"] == "stale_attempt"


async def test__heartbeat__lease_taken_by_another_runner__409(env: _Env) -> None:
    headers, job_id, envelope = await _leased(env)
    env.clock.advance(46)
    await env.queue.requeue_expired()
    second = await env.register()
    assert (await _poll(env, second))["envelope"] is not None

    response = await _beat(env, headers, job_id, envelope)

    assert response.status_code == 409
    assert response.json()["code"] == "stale_attempt"


async def test__heartbeat__bad_or_foreign_job_token__401(env: _Env) -> None:
    headers, job_id, envelope = await _leased(env)
    other = await env.register()

    bad = await env.client.post(
        f"/api/runner/v1/jobs/{job_id}/heartbeat",
        json={"attempt": 1},
        headers={**headers, "X-Job-Token": "garbage"},
    )
    foreign = await _beat(env, other, job_id, envelope)

    for response in (bad, foreign):
        assert response.status_code == 401
        assert response.json()["code"] == "job_token_invalid"


async def test__heartbeat__unknown_job__404(env: _Env) -> None:
    headers, job_id, envelope = await _leased(env)
    signer = JobTokenSigner([b"k" * 32])
    runner = (await env.registry.list_runners(_ADMIN))[0]
    ghost = uuid4()
    token = signer.sign(str(ghost), runner.id, env.clock.now + timedelta(hours=1))

    response = await env.client.post(
        f"/api/runner/v1/jobs/{ghost}/heartbeat", json={"attempt": 1}, headers={**headers, "X-Job-Token": token}
    )

    assert response.status_code == 404
    assert response.json()["code"] == "job_not_found"
