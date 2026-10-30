"""Локальная Студия как личный раннер: настоящий супервизор и цикл раннера против маршрутов сервера в процессе.

Сервер здесь лёгкий (очередь и реестр раннеров в памяти), сеть заменена ASGI-транспортом. Проверяется
путь Студии целиком: токен из интерфейса, регистрация, опрос, взятая задача, выключение переключателя.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
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
from hse_doc_studio.core.jobs.enums import JobState
from hse_doc_studio.core.jobs.queue import EnqueueRequest
from hse_doc_studio.core.jobs.runners import JobTokenSigner
from hse_doc_studio.core.jobs.wire import JobEnvelope
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.remote_runner import RemoteRunnerSettings, RemoteRunnerState
from hse_doc_studio.infra.remote_runner.runner_session import runner_session_factory
from hse_doc_studio.infra.remote_runner.supervisor import RemoteRunnerSupervisor
from hse_doc_studio.infra.runner.pairing_client import RunnerPairingClient
from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService
from hse_doc_studio.use_cases.jobs.runner_jobs import RunnerJobService
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry
from hse_doc_studio.use_cases.jobs.wakeup import JobWakeup

from tests.fakes.auth import InMemoryAuditLog
from tests.fakes.job_queue import InMemoryJobQueue
from tests.fakes.runners import InMemoryRegistrationTokenRepository, InMemoryRunnerRepository
from tests.unit.core.jobs.samples import make_verify_spec
from tests.unit.infra.remote_runner.fakes import FakeEnvironment, MemorySettingsStore, eventually

_ADMIN = Actor(kind="user", id="admin", is_instance_admin=True)
_SERVER = "http://localhost:8000"


class _Uow:
    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        yield


@dataclass
class _World:
    queue: InMemoryJobQueue
    wakeup: JobWakeup
    registry: RunnerRegistry
    runners: InMemoryRunnerRepository
    supervisor: RemoteRunnerSupervisor
    store: MemorySettingsStore
    polls: list[str]


class _CountingTransport(httpx.AsyncBaseTransport):
    def __init__(self, app: FastAPI, polls: list[str]) -> None:
        self._inner = httpx.ASGITransport(app=app)
        self._polls = polls

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/poll"):
            self._polls.append(request.url.path)
        return await self._inner.handle_async_request(request)


@pytest_asyncio.fixture
async def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_World]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    queue = InMemoryJobQueue(lambda: datetime.now(UTC))
    runners = InMemoryRunnerRepository()
    registry = RunnerRegistry(runners, InMemoryRegistrationTokenRepository(), InMemoryAuditLog(), _Uow())
    wakeup = JobWakeup()
    service = RunnerJobService(
        queue,
        JobQueueService(queue, lease_s=45.0, timeout_grace_s=15.0),
        runners,
        JobTokenSigner([b"k" * 32]),
        wakeup,
        lease_s=45.0,
        timeout_grace_s=15.0,
        poll_interval_s=0.05,
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
    polls: list[str] = []
    store = MemorySettingsStore(RemoteRunnerSettings())
    supervisor = RemoteRunnerSupervisor(
        store,
        runner_dir=tmp_path / "remote-runner",
        default_name="studio-mac",
        pairing_client=lambda url: RunnerPairingClient(url, version="0.3.0"),
        session_factory=runner_session_factory(cache_volume="tex-cache", transport=_CountingTransport(app, polls)),
        # Docker есть, образа TeX нет: Студия объявляет verify и pack без tex.
        environment=FakeEnvironment(image=False),
    )
    await supervisor.start()
    yield _World(queue, wakeup, registry, runners, supervisor, store, polls)
    await supervisor.stop()
    await container.close()


async def _enqueue_verify(world: _World) -> UUID:
    spec = make_verify_spec()
    envelope = JobEnvelope(spec=spec, manifest=(), timeout_s=600.0, attempt=1, job_token="x", actor_role=Role.owner)
    payload = {k: v for k, v in encode_envelope(envelope).items() if k not in {"job_token", "attempt"}}
    job_id = uuid4()
    await world.queue.enqueue(
        EnqueueRequest(
            job_id=job_id,
            kind=spec.kind,
            project_id=spec.project_id,
            user_id=uuid4(),
            tags=frozenset(spec.tags),
            payload=payload,
            max_attempts=1,
            timeout_s=600.0,
        )
    )
    world.wakeup.notify()
    return job_id


async def test__token_from_ui__studio_registers_and_takes_jobs(world: _World) -> None:
    token = (await world.registry.create_registration_token(_ADMIN)).secret

    await world.supervisor.use_token(_SERVER, token)

    await eventually(lambda: world.supervisor.status().state is RemoteRunnerState.online, timeout_s=10)
    status = world.supervisor.status()
    assert status.paired is True
    registered = await world.runners.get(status.runner_id or "")
    assert registered is not None
    assert registered.name == "studio-mac"
    assert "tex" not in registered.tags
    job_id = await _enqueue_verify(world)

    async def taken() -> bool:
        job = await world.queue.get(job_id)
        return job is not None and job.runner_id is not None and job.runner_id == UUID(status.runner_id or "")

    for _ in range(200):
        if await taken():
            break
        await asyncio.sleep(0.05)
    job = await world.queue.get(job_id)
    assert job is not None
    assert job.state is not JobState.queued
    assert job.runner_id == UUID(status.runner_id or "")


async def test__toggle_off__studio_stops_polling(world: _World) -> None:
    token = (await world.registry.create_registration_token(_ADMIN)).secret
    await world.supervisor.use_token(_SERVER, token)
    await eventually(lambda: world.supervisor.status().state is RemoteRunnerState.online, timeout_s=10)

    await world.supervisor.apply(replace(world.store.settings, enabled=False))

    polls = len(world.polls)
    await asyncio.sleep(0.3)
    assert len(world.polls) == polls
    assert world.supervisor.status().state is RemoteRunnerState.off
