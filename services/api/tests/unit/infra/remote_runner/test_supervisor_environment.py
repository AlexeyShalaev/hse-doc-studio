from __future__ import annotations

import asyncio
from pathlib import Path

from hse_doc_studio.core.remote_runner import RemoteRunnerSettings, RemoteRunnerState
from hse_doc_studio.infra.remote_runner.session import RunnerSessionFatal, SessionFatalCode
from hse_doc_studio.infra.remote_runner.supervisor import RemoteRunnerSupervisor
from hse_doc_studio.infra.runner.pairing_client import RunnerPairingClient

from tests.unit.infra.remote_runner.fake_pairing_api import FakePairingServer
from tests.unit.infra.remote_runner.fakes import (
    FakeEnvironment,
    FakeSessions,
    MemorySettingsStore,
    eventually,
    save_identity,
)

_URL = "https://studio.example.org"


def _supervisor(
    tmp_path: Path, env: FakeEnvironment, sessions: FakeSessions, **kwargs: object
) -> RemoteRunnerSupervisor:
    runner_dir = tmp_path / "remote-runner"
    save_identity(runner_dir, _URL)
    server = FakePairingServer()

    async def sleep(_delay: float) -> None:
        await asyncio.sleep(0.01)

    return RemoteRunnerSupervisor(
        MemorySettingsStore(RemoteRunnerSettings(enabled=True, server_url=_URL, **kwargs)),  # type: ignore[arg-type]
        runner_dir=runner_dir,
        default_name="studio-mac",
        pairing_client=lambda url: RunnerPairingClient(url, version="0.3.0", transport=server.transport()),
        session_factory=sessions,
        environment=env,
        sleep=sleep,
    )


async def test__docker_and_image_ready__declares_tex_and_gate_open(tmp_path: Path) -> None:
    sessions = FakeSessions()
    supervisor = _supervisor(tmp_path, FakeEnvironment(), sessions)

    await supervisor.start()

    await eventually(lambda: supervisor.status().state is RemoteRunnerState.online)
    spec = sessions.specs[0]
    assert (spec.tex_available, spec.tex_image) == (True, "ghcr.io/example/texlive:2026")
    assert spec.gate() is True
    status = supervisor.status()
    assert (status.docker.value, status.tex_image.value) == ("ok", "ready")
    await supervisor.stop()


async def test__docker_missing__no_tex_and_gate_closed(tmp_path: Path) -> None:
    sessions = FakeSessions()
    supervisor = _supervisor(tmp_path, FakeEnvironment(docker=False, image=False), sessions)

    await supervisor.start()

    await eventually(lambda: len(sessions.specs) == 1)
    assert sessions.specs[0].tex_available is False
    assert sessions.specs[0].gate() is False
    status = supervisor.status()
    assert (status.docker.value, status.tex_image.value) == ("missing", "missing")
    await supervisor.stop()


async def test__image_missing__no_tex_but_gate_open(tmp_path: Path) -> None:
    sessions = FakeSessions()
    supervisor = _supervisor(tmp_path, FakeEnvironment(image=False), sessions)

    await supervisor.start()

    await eventually(lambda: len(sessions.specs) == 1)
    assert (sessions.specs[0].tex_available, sessions.specs[0].gate()) == (False, True)
    assert supervisor.status().tex_image.value == "missing"
    await supervisor.stop()


async def test__yield_to_local__local_build_running__gate_closed(tmp_path: Path) -> None:
    env = FakeEnvironment(busy=True)
    sessions = FakeSessions()
    supervisor = _supervisor(tmp_path, env, sessions)
    await supervisor.start()
    await eventually(lambda: len(sessions.specs) == 1)

    assert sessions.specs[0].gate() is False
    env.busy = False
    assert sessions.specs[0].gate() is True
    await supervisor.stop()


async def test__yield_to_local_off__local_build_running__gate_open(tmp_path: Path) -> None:
    sessions = FakeSessions()
    supervisor = _supervisor(tmp_path, FakeEnvironment(busy=True), sessions, yield_to_local=False)

    await supervisor.start()

    await eventually(lambda: len(sessions.specs) == 1)
    assert sessions.specs[0].gate() is True
    await supervisor.stop()


async def test__image_installed_later__session_restarts_with_tex(tmp_path: Path) -> None:
    env = FakeEnvironment(image=False)
    sessions = FakeSessions()
    supervisor = _supervisor(tmp_path, env, sessions)
    await supervisor.start()
    await eventually(lambda: len(sessions.specs) == 1)

    env.image = True

    await eventually(lambda: len(sessions.specs) == 2)
    assert sessions.specs[1].tex_available is True
    assert sessions.sessions[0].stopped is True
    await supervisor.stop()


async def test__server_refused_with_limit__error_with_server_code_and_no_retry(tmp_path: Path) -> None:
    sessions = FakeSessions()
    sessions.fatal = [RunnerSessionFatal(SessionFatalCode.refused, "runner_limit")]
    supervisor = _supervisor(tmp_path, FakeEnvironment(), sessions)

    await supervisor.start()

    await eventually(lambda: supervisor.status().state is RemoteRunnerState.error)
    assert supervisor.status().detail_code == "runner_limit"
    await asyncio.sleep(0.05)
    assert len(sessions.specs) == 1
