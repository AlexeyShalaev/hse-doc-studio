"""Канал команд и диск раннера поверх настоящих маршрутов (`/control/*`, `/disk`): хранилища в памяти."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.guards import install_exception_handlers
from hse_doc_studio.api.routers.server_routers import include_server_routers
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.jobs.disk import (
    MAX_DISK_REPORT_BYTES,
    DiskCleanupPayload,
    DiskTarget,
    RunnerCommand,
    RunnerCommandKind,
    RunnerCommandState,
)
from hse_doc_studio.core.jobs.wire import RUNNER_PROTOCOL_VERSION
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.use_cases.jobs.runner_control import RunnerCommandWakeup, RunnerControlService
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry
from httpx import ASGITransport, AsyncClient

from tests.fakes.auth import InMemoryAuditLog
from tests.fakes.runner_commands import InMemoryRunnerCommandRepository, InMemoryRunnerDiskStore
from tests.fakes.runners import InMemoryRegistrationTokenRepository, InMemoryRunnerRepository

_ADMIN = Actor(kind="user", id="admin", is_instance_admin=True)
_FIXTURES = Path(__file__).resolve().parents[6] / "contracts" / "runner" / "fixtures"
_API = "/api/runner/v1"


def _fixture(schema: str, name: str) -> dict[str, Any]:
    return dict(json.loads((_FIXTURES / schema / f"{name}.json").read_text(encoding="utf-8")))


class _Uow:
    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        yield


@dataclass
class _Env:
    client: AsyncClient
    registry: RunnerRegistry
    runners: InMemoryRunnerRepository
    service: RunnerControlService

    async def runner(self, features: list[str]) -> tuple[dict[str, str], str]:
        created = await self.registry.create_registration_token(_ADMIN)
        registered = await self.client.post(
            f"{_API}/register",
            json={
                "name": "r",
                "protocol": RUNNER_PROTOCOL_VERSION,
                "version": "0.22.0",
                "tags": ["compile"],
                "concurrency": 1,
                "resource_class": "standard",
            },
            headers={"Authorization": f"Bearer {created.secret}"},
        )
        headers = {"Authorization": f"Bearer {registered.json()['runner_token']}"}
        announced = await self.client.post(
            f"{_API}/announce",
            json={
                "name": "r",
                "version": "0.22.0",
                "tags": ["compile"],
                "concurrency": 1,
                "ai_concurrency": 0,
                "host_kind": "cli",
                "features": ["announce", *features],
                "ai_endpoints": [],
            },
            headers=headers,
        )
        assert announced.status_code == 200
        return headers, registered.json()["runner_id"]

    async def cleanup(self, runner_id: str) -> RunnerCommand:
        runner = await self.runners.get(runner_id)
        assert runner is not None
        return await self.service.enqueue(
            runner,
            RunnerCommandKind.disk_cleanup,
            DiskCleanupPayload(targets=(DiskTarget.dangling_images,)),
            created_by="admin",
        )


@pytest_asyncio.fixture
async def env(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Env]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    runners = InMemoryRunnerRepository()
    registry = RunnerRegistry(runners, InMemoryRegistrationTokenRepository(), InMemoryAuditLog(), _Uow())
    service = RunnerControlService(
        InMemoryRunnerCommandRepository(runners),
        InMemoryRunnerDiskStore(runners),
        runners,
        RunnerCommandWakeup(),
        poll_interval_s=0.05,
    )

    class _Provider(Provider):
        scope = Scope.APP

        @provide
        def registry_(self) -> RunnerRegistry:
            return registry

        @provide
        def service_(self) -> RunnerControlService:
            return service

    app = FastAPI()
    include_server_routers(app)
    install_exception_handlers(app)
    container = make_async_container(_Provider(), FastapiProvider())
    setup_dishka(container, app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield _Env(client, registry, runners, service)
    await container.close()


async def test__announce__server_negotiates_control_and_disk(env: _Env) -> None:
    headers, _ = await env.runner([])

    answer = await env.client.post(
        f"{_API}/announce",
        json={
            "name": "r",
            "version": "0.22.0",
            "tags": ["compile"],
            "concurrency": 1,
            "ai_concurrency": 0,
            "host_kind": "cli",
            "features": ["announce", "control", "disk"],
            "ai_endpoints": [],
        },
        headers=headers,
    )

    assert {"control", "disk"} <= set(answer.json()["server_features"])


async def test__control__cleanup_round_trip_over_http(env: _Env) -> None:
    headers, runner_id = await env.runner(["control", "disk"])
    waiting = asyncio.create_task(env.client.post(f"{_API}/control/poll", json={"wait_s": 10}, headers=headers))
    await asyncio.sleep(0.1)
    command = await env.cleanup(runner_id)

    polled = await asyncio.wait_for(waiting, 3)
    envelope = polled.json()["command"]
    running = await env.client.post(
        f"{_API}/control/{command.id}/progress", json=_fixture("CommandProgressRequestBody", "running"), headers=headers
    )
    await env.service.cancel(runner_id, command.id)
    told = await env.client.post(
        f"{_API}/control/{command.id}/progress", json=_fixture("CommandProgressRequestBody", "running"), headers=headers
    )
    final = {**_fixture("CommandProgressRequestBody", "running"), "state": "cancelled"}
    closed = await env.client.post(f"{_API}/control/{command.id}/progress", json=final, headers=headers)
    repeated = await env.client.post(f"{_API}/control/{command.id}/progress", json=final, headers=headers)

    assert polled.status_code == 200
    assert envelope["id"] == str(command.id)
    assert envelope["kind"] == "disk.cleanup"
    assert envelope["payload"] == {"targets": ["dangling_images"], "include_rollback": False}
    assert running.json() == {"cancel": False}
    assert told.json() == {"cancel": True}
    assert closed.json() == repeated.json() == {"cancel": False}
    assert (await env.service.get(runner_id, command.id)).state is RunnerCommandState.cancelled


async def test__control__empty_poll_answers_null(env: _Env) -> None:
    headers, _ = await env.runner(["control", "disk"])

    response = await env.client.post(f"{_API}/control/poll", json={"wait_s": 0}, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"command": None}


async def test__control__closed_and_foreign_commands__409_and_404(env: _Env) -> None:
    headers, runner_id = await env.runner(["control", "disk"])
    other_headers, _ = await env.runner(["control", "disk"])
    command = await env.cleanup(runner_id)
    await env.client.post(f"{_API}/control/poll", json={"wait_s": 0}, headers=headers)
    done = {**_fixture("CommandProgressRequestBody", "running"), "state": "done"}
    await env.client.post(f"{_API}/control/{command.id}/progress", json=done, headers=headers)

    finished = await env.client.post(
        f"{_API}/control/{command.id}/progress", json=_fixture("CommandProgressRequestBody", "error"), headers=headers
    )
    foreign = await env.client.post(f"{_API}/control/{command.id}/progress", json=done, headers=other_headers)
    unknown = await env.client.post(f"{_API}/control/{uuid4()}/progress", json=done, headers=headers)

    assert (finished.status_code, finished.json()["code"]) == (409, "command_finished")
    assert (foreign.status_code, foreign.json()["code"]) == (404, "command_not_found")
    assert (unknown.status_code, unknown.json()["code"]) == (404, "command_not_found")


async def test__control_and_disk__without_negotiated_features__409(env: _Env) -> None:
    headers, _ = await env.runner([])

    poll = await env.client.post(f"{_API}/control/poll", json={"wait_s": 0}, headers=headers)
    progress = await env.client.post(
        f"{_API}/control/{uuid4()}/progress", json=_fixture("CommandProgressRequestBody", "running"), headers=headers
    )
    disk = await env.client.post(f"{_API}/disk", json=_fixture("RunnerDiskReportBody", "docker"), headers=headers)

    for response in (poll, progress, disk):
        assert (response.status_code, response.json()["code"]) == (409, "feature_not_negotiated")


async def test__control__without_token__401(env: _Env) -> None:
    response = await env.client.post(f"{_API}/control/poll", json={"wait_s": 0})

    assert response.status_code == 401


@pytest.mark.parametrize("name", ["docker", "docker_unavailable", "kubernetes", "desktop"])
async def test__disk__report_is_stored(env: _Env, name: str) -> None:
    headers, runner_id = await env.runner(["control", "disk"])

    response = await env.client.post(f"{_API}/disk", json=_fixture("RunnerDiskReportBody", name), headers=headers)

    assert response.status_code == 204
    stored = await env.service.disk(runner_id)
    assert stored is not None
    assert stored.report.measured_at.isoformat().startswith(_fixture("RunnerDiskReportBody", name)["measured_at"][:19])


async def test__disk__extra_fields_and_inconsistent_report__422(env: _Env) -> None:
    headers, runner_id = await env.runner(["disk"])
    body = _fixture("RunnerDiskReportBody", "docker")

    extra = await env.client.post(f"{_API}/disk", json={**body, "data_dir": "/srv/runner"}, headers=headers)
    broken = await env.client.post(f"{_API}/disk", json={**body, "docker": None}, headers=headers)
    garbage = await env.client.post(
        f"{_API}/disk", content=b"{not json", headers={**headers, "Content-Type": "application/json"}
    )

    assert [r.status_code for r in (extra, broken, garbage)] == [422, 422, 422]
    assert await env.service.disk(runner_id) is None


async def test__disk__larger_than_64_kib__413_before_parsing(env: _Env) -> None:
    headers, runner_id = await env.runner(["disk"])
    body = _fixture("RunnerDiskReportBody", "docker")
    padded = json.dumps(body).encode() + b" " * MAX_DISK_REPORT_BYTES

    declared = await env.client.post(
        f"{_API}/disk", content=padded, headers={**headers, "Content-Type": "application/json"}
    )

    async def chunks() -> AsyncIterator[bytes]:
        yield padded

    streamed = await env.client.post(
        f"{_API}/disk", content=chunks(), headers={**headers, "Content-Type": "application/json"}
    )

    assert (declared.status_code, declared.json()["code"]) == (413, "disk_report_too_large")
    assert (streamed.status_code, streamed.json()["code"]) == (413, "disk_report_too_large")
    assert await env.service.disk(runner_id) is None
