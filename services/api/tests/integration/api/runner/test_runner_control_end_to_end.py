"""Канал команд целиком: настоящий цикл раннера с `RunnerControlLoop` против настоящих маршрутов `/control/*`, `/disk`.

Хранилища сервера в памяти, диск раннера настоящий (`RunnerDiskService`) на фейковом Docker. Опрос задач закрыт
шлюзом: здесь проверяется только канал команд (storage-cleanup.md, 6.2, 6.3).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

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
    CommandStepStatus,
    DiskCleanupPayload,
    DiskMeasurePayload,
    DiskTarget,
    RunnerCommand,
    RunnerCommandKind,
    RunnerCommandPayload,
    RunnerCommandState,
)
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.runner.backoff import Backoff
from hse_doc_studio.infra.runner.client import RunnerClient
from hse_doc_studio.infra.runner.control import ControlLoopConfig, RunnerControlLoop
from hse_doc_studio.infra.runner.disk import RunnerDiskService
from hse_doc_studio.infra.runner.loop import RunnerLoop, RunnerLoopConfig
from hse_doc_studio.use_cases.jobs.runner_control import RunnerCommandWakeup, RunnerControlService
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry
from httpx import ASGITransport

from tests.fakes.auth import InMemoryAuditLog
from tests.fakes.runner_commands import InMemoryRunnerCommandRepository, InMemoryRunnerDiskStore
from tests.fakes.runners import InMemoryRegistrationTokenRepository, InMemoryRunnerRepository
from tests.unit.infra.runner.test_runner_disk import _docker, _Probe, _service, _System, _usage
from tests.unit.infra.runner.test_runner_loop import FakeExecutor, until

_ADMIN = Actor(kind="user", id="admin", is_instance_admin=True)


class _Uow:
    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        yield


@dataclass
class _Stack:
    service: RunnerControlService
    runners: InMemoryRunnerRepository
    system: _System
    disk: RunnerDiskService
    loop: RunnerLoop
    client: RunnerClient
    task: asyncio.Task[None] | None = None

    @property
    def runner_id(self) -> str:
        runner_id = self.loop.runner_id
        assert runner_id is not None
        return runner_id

    def start(self) -> None:
        self.task = asyncio.create_task(self.loop.run())

    async def stop(self) -> None:
        if self.task is None:
            return
        self.loop.request_stop()
        await asyncio.wait_for(self.task, 10)
        self.task = None

    async def enqueue(self, kind: RunnerCommandKind, payload: RunnerCommandPayload) -> RunnerCommand:
        runner = await self.runners.get(self.runner_id)
        assert runner is not None
        return await self.service.enqueue(runner, kind, payload, created_by="admin")

    async def command(self, command: RunnerCommand) -> RunnerCommand:
        return await self.service.get(self.runner_id, command.id)

    async def until_state(self, command: RunnerCommand, *states: RunnerCommandState) -> RunnerCommand:
        current = command
        async with asyncio.timeout(5):
            while current.state not in states:
                await asyncio.sleep(0.02)
                current = await self.command(command)
        return current


@pytest_asyncio.fixture
async def stack(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[_Stack]:
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

    created = await registry.create_registration_token(_ADMIN)
    system = _System()
    disk = _service(tmp_path, _docker(_Probe(_usage()), system))
    client = RunnerClient(
        "http://test",
        created.secret,
        version="0.22.0",
        transport=ASGITransport(app=app),
        backoff_factory=lambda: Backoff(base_s=0.01, cap_s=0.05),
    )
    fast = lambda: Backoff(base_s=0.01, cap_s=0.05, jitter=0.0)  # noqa: E731
    control = RunnerControlLoop(
        client,
        disk,
        ControlLoopConfig(
            wait_s=1,
            min_poll_interval_s=0.01,
            progress_interval_s=0.01,
            # Повтор хода на долгом шаге: по нему раннер узнаёт об остановке, пока шаг стоит.
            progress_keepalive_s=0.05,
            backoff_factory=fast,
        ),
    )
    loop = RunnerLoop(
        client,
        FakeExecutor(),
        RunnerLoopConfig(
            name="r",
            version="0.22.0",
            poll_wait_s=0,
            drain_timeout_s=2.0,
            backoff_factory=fast,
            # Опрос задач закрыт: у этого сервера только канал команд.
            gate=lambda: False,
            gate_recheck_s=0.02,
        ),
        control=control,
    )
    result = _Stack(service, runners, system, disk, loop, client)
    try:
        yield result
    finally:
        await result.stop()
        await client.aclose()
        await container.close()


def _cancel_requested(stack: _Stack) -> bool:
    run = stack.disk.current()
    return run is not None and run.cancel_requested


async def _started(stack: _Stack) -> None:
    stack.start()
    await until(lambda: stack.loop.runner_id is not None)
    async with asyncio.timeout(5):
        while await stack.service.disk(stack.runner_id) is None:
            await asyncio.sleep(0.02)


async def test__runner_reports_disk_after_announce_and_answers_measure(stack: _Stack) -> None:
    await _started(stack)
    first = await stack.service.disk(stack.runner_id)
    assert first is not None
    assert first.report.docker is not None

    command = await stack.enqueue(RunnerCommandKind.disk_measure, DiskMeasurePayload())
    done = await stack.until_state(command, RunnerCommandState.done, RunnerCommandState.error)

    assert done.state is RunnerCommandState.done
    assert done.progress is not None
    assert done.progress.steps == ()


async def test__cleanup_runs_on_the_runner_and_closes_done(stack: _Stack) -> None:
    await _started(stack)

    command = await stack.enqueue(
        RunnerCommandKind.disk_cleanup, DiskCleanupPayload(targets=(DiskTarget.build_cache, DiskTarget.dangling_images))
    )
    done = await stack.until_state(command, RunnerCommandState.done, RunnerCommandState.error)

    assert done.state is RunnerCommandState.done
    assert done.progress is not None
    assert done.progress.freed_bytes == 70
    assert stack.system.calls == ["build_cache", "dangling_images"]


async def test__admin_stop_reaches_the_runner_after_the_current_step(stack: _Stack) -> None:
    stack.system.gate = asyncio.Event()
    await _started(stack)
    command = await stack.enqueue(
        RunnerCommandKind.disk_cleanup, DiskCleanupPayload(targets=(DiskTarget.build_cache, DiskTarget.dangling_images))
    )
    await stack.until_state(command, RunnerCommandState.running)

    await stack.service.cancel(stack.runner_id, command.id)
    # Остановку раннер узнаёт в ответе на повтор хода, пока первый шаг стоит.
    await until(lambda: _cancel_requested(stack))
    stack.system.gate.set()
    closed = await stack.until_state(command, RunnerCommandState.cancelled, RunnerCommandState.done)

    assert closed.state is RunnerCommandState.cancelled
    assert closed.progress is not None
    assert [step.status for step in closed.progress.steps] == [CommandStepStatus.done, CommandStepStatus.skipped]


async def test__runner_stop_closes_the_running_cleanup_cancelled_not_lost(stack: _Stack) -> None:
    stack.system.gate = asyncio.Event()
    await _started(stack)
    command = await stack.enqueue(
        RunnerCommandKind.disk_cleanup, DiskCleanupPayload(targets=(DiskTarget.build_cache, DiskTarget.dangling_images))
    )
    await stack.until_state(command, RunnerCommandState.running)

    stopping = asyncio.create_task(stack.stop())
    await asyncio.sleep(0.05)
    stack.system.gate.set()
    await stopping
    closed = await stack.command(command)

    assert closed.state is RunnerCommandState.cancelled
