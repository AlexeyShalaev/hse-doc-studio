"""Поддельные сессии раннера для тестов супервизора: без сети и Docker, исход задаётся тестом."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path

from hse_doc_studio.core.jobs.wire import RunnerRegisterResponse
from hse_doc_studio.core.remote_runner import RemoteRunnerSettings
from hse_doc_studio.infra.remote_runner.session import (
    IRunnerSession,
    IRunnerSessionListener,
    LocalAiEndpoint,
    RunnerSessionFatal,
    RunnerSessionSpec,
    SessionState,
)
from hse_doc_studio.infra.runner.identity import RunnerIdentityStore

RUNNER_ID = "4f1c2b3a5d6e47f89a0b1c2d3e4f5a6b"
RUNNER_TOKEN = "hsrn_runner-secret"  # noqa: S105 — тестовое значение


class MemorySettingsStore:
    def __init__(self, settings: RemoteRunnerSettings | None = None) -> None:
        self.settings = settings or RemoteRunnerSettings()
        self.saves = 0

    async def load(self) -> RemoteRunnerSettings:
        return self.settings

    async def save(self, settings: RemoteRunnerSettings) -> None:
        self.settings = settings
        self.saves += 1


class FakeSession:
    def __init__(self, spec: RunnerSessionSpec, listener: IRunnerSessionListener, owner: FakeSessions) -> None:
        self.spec = spec
        self._listener = listener
        self._owner = owner
        self._stop = asyncio.Event()
        self.running_jobs = 0
        self.stopped = False
        self.announced: list[tuple[str, ...]] = []

    async def run(self) -> None:
        if self._owner.fatal:
            raise self._owner.fatal.pop(0)
        if self.spec.registration_token is not None:
            # Как RunnerClient: личность пишется на диск, токен регистрации больше не нужен.
            save_identity(self.spec.data_dir, self.spec.server_url)
            self._listener.on_registered()
        self._listener.on_session_state(self._owner.state_after_start)
        await self._stop.wait()
        self.stopped = True

    def request_stop(self) -> None:
        self._stop.set()

    async def reannounce(self, ai_endpoints: tuple[LocalAiEndpoint, ...]) -> None:
        self.announced.append(tuple(e.name for e in ai_endpoints))


class FakeSessions:
    """Фабрика сессий: запоминает спецификации, по очереди бросает заданные отказы."""

    def __init__(self) -> None:
        self.specs: list[RunnerSessionSpec] = []
        self.sessions: list[FakeSession] = []
        self.fatal: list[RunnerSessionFatal] = []
        self.state_after_start = SessionState.online

    def __call__(
        self, spec: RunnerSessionSpec, listener: IRunnerSessionListener
    ) -> AbstractAsyncContextManager[IRunnerSession]:
        return self._open(spec, listener)

    @asynccontextmanager
    async def _open(self, spec: RunnerSessionSpec, listener: IRunnerSessionListener) -> AsyncIterator[IRunnerSession]:
        self.specs.append(spec)
        session = FakeSession(spec, listener, self)
        self.sessions.append(session)
        yield session


def save_identity(data_dir: Path, server_url: str) -> None:
    RunnerIdentityStore(data_dir).save(
        server_url,
        RunnerRegisterResponse(
            runner_id=RUNNER_ID, runner_token=RUNNER_TOKEN, lease_s=45, heartbeat_s=10, max_poll_wait_s=25
        ),
    )


async def eventually(predicate: Callable[[], bool], timeout_s: float = 3.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not reached")
        await asyncio.sleep(0.005)


class FakeEnvironment:
    def __init__(self, *, docker: bool = True, image: bool = True, busy: bool = False) -> None:
        self.docker = docker
        self.image = image
        self.busy = busy

    async def docker_available(self) -> bool:
        return self.docker

    async def tex_image(self) -> str:
        return "ghcr.io/example/texlive:2026"

    async def image_present(self, image: str) -> bool:
        return self.image

    def local_busy(self) -> bool:
        return self.busy
