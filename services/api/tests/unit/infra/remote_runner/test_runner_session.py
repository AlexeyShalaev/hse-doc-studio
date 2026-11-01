from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from hse_doc_studio.infra.remote_runner.runner_session import cloud_cache_volume, runner_session_factory
from hse_doc_studio.infra.remote_runner.session import (
    RunnerSessionFatal,
    RunnerSessionSpec,
    SessionFatalCode,
    SessionState,
)
from hse_doc_studio.infra.runner.identity import IDENTITY_FILE, RunnerIdentityStore

from tests.unit.infra.remote_runner.fakes import eventually
from tests.unit.infra.runner.fake_runner_api import TOKEN, FakeRunnerState, SwitchTransport, create_fake_app

_URL = "http://api"


class Listener:
    def __init__(self) -> None:
        self.states: list[SessionState] = []
        self.registered = 0

    def on_session_state(self, state: SessionState) -> None:
        self.states.append(state)

    def on_registered(self) -> None:
        self.registered += 1


def _spec(data_dir: Path, *, token: str | None = TOKEN, gate: bool = True, tex: bool = False) -> RunnerSessionSpec:
    return RunnerSessionSpec(
        server_url=_URL,
        registration_token=token,
        name="MacBook",
        concurrency=1,
        data_dir=data_dir,
        tex_image="texlive:test",
        tex_available=tex,
        gate=lambda: gate,
    )


async def _run_until(session: object, predicate: object) -> None:
    task = asyncio.create_task(session.run())  # type: ignore[attr-defined]
    try:
        await eventually(predicate)  # type: ignore[arg-type]
    finally:
        session.request_stop()  # type: ignore[attr-defined]
        await asyncio.wait_for(task, 5)


async def test__session__registers_saves_identity_and_reports_online(tmp_path: Path) -> None:
    state = FakeRunnerState()
    listener = Listener()
    factory = runner_session_factory(cache_volume="tex-cache", transport=SwitchTransport(create_fake_app(state)))

    async with factory(_spec(tmp_path), listener) as session:
        await _run_until(session, lambda: SessionState.online in listener.states)

    assert listener.registered == 1
    assert RunnerIdentityStore(tmp_path).load(_URL) is not None
    registration = state.registrations[0]
    assert registration["name"] == "MacBook"
    assert "tex" not in registration["tags"]


async def test__session__tex_available__declares_tex_tag(tmp_path: Path) -> None:
    state = FakeRunnerState()
    factory = runner_session_factory(cache_volume="tex-cache", transport=SwitchTransport(create_fake_app(state)))

    async with factory(_spec(tmp_path, tex=True), Listener()) as session:
        await _run_until(session, lambda: state.polls > 0)

    assert "tex" in state.registrations[0]["tags"]


async def test__session__gate_closed__polls_never_reach_server(tmp_path: Path) -> None:
    state = FakeRunnerState()
    factory = runner_session_factory(cache_volume="tex-cache", transport=SwitchTransport(create_fake_app(state)))

    async with factory(_spec(tmp_path, gate=False), Listener()) as session:
        await _run_until(session, lambda: len(state.registrations) == 1)
        await asyncio.sleep(0.1)

    assert state.polls == 0


async def test__session__server_down__reports_offline(tmp_path: Path) -> None:
    transport = SwitchTransport(create_fake_app(FakeRunnerState()))
    listener = Listener()
    factory = runner_session_factory(cache_volume="tex-cache", transport=transport)

    async with factory(_spec(tmp_path), listener) as session:
        task = asyncio.create_task(session.run())
        await eventually(lambda: SessionState.online in listener.states)
        transport.down = True
        await eventually(lambda: listener.states[-1] is SessionState.offline)
        session.request_stop()
        await asyncio.wait_for(task, 5)


async def test__session__revoked_token__raises_unauthorized(tmp_path: Path) -> None:
    (tmp_path / IDENTITY_FILE).write_text(
        '{"api_url": "http://api", "runner_id": "r1", "runner_token": "hsrn_revoked"}', encoding="utf-8"
    )
    factory = runner_session_factory(
        cache_volume="tex-cache", transport=SwitchTransport(create_fake_app(FakeRunnerState()))
    )

    async with factory(_spec(tmp_path, token=None), Listener()) as session:
        with pytest.raises(RunnerSessionFatal) as caught:
            await asyncio.wait_for(session.run(), 5)

    assert caught.value.code is SessionFatalCode.unauthorized


def test__cloud_cache_volume__differs_from_the_local_one() -> None:
    """Облачные сборки (в том числе соавторов хозяина) не делят записываемый HOME с локальными проектами."""
    assert cloud_cache_volume("hse-studio-texmf") == "hse-studio-texmf-cloud"
