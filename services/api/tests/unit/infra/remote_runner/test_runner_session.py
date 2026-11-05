from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace
from pathlib import Path

import pytest
from hse_doc_studio.infra.remote_runner.runner_session import SessionFonts, cloud_cache_volume, runner_session_factory
from hse_doc_studio.infra.remote_runner.session import (
    RunnerSessionFatal,
    RunnerSessionSpec,
    SessionFatalCode,
    SessionState,
)
from hse_doc_studio.infra.runner.identity import IDENTITY_FILE, RunnerIdentityStore

from tests.unit.infra.remote_runner.fakes import eventually
from tests.unit.infra.runner.fake_runner_api import (
    TOKEN,
    FakeRunnerState,
    SwitchTransport,
    create_fake_app,
    envelope_body,
)

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


async def test__session__tex_available__host_fonts_are_adopted_once_before_the_loop_starts(tmp_path: Path) -> None:
    state = FakeRunnerState()
    calls: list[str] = []

    async def ensure() -> None:
        calls.append("adopt")

    fonts = SessionFonts(tmp_path / "fonts", str(tmp_path / "fonts"), "/usr/local/share/fonts/hse", ensure)
    factory = runner_session_factory(
        cache_volume="tex-cache", transport=SwitchTransport(create_fake_app(state)), fonts=fonts
    )

    async with factory(_spec(tmp_path, tex=True), Listener()) as session:
        await _run_until(session, lambda: state.polls > 0)

    assert calls == ["adopt"]


async def test__session__no_docker__host_fonts_are_not_touched(tmp_path: Path) -> None:
    state = FakeRunnerState()
    calls: list[str] = []

    async def ensure() -> None:
        calls.append("adopt")

    fonts = SessionFonts(tmp_path / "fonts", str(tmp_path / "fonts"), "/usr/local/share/fonts/hse", ensure)
    factory = runner_session_factory(
        cache_volume="tex-cache", transport=SwitchTransport(create_fake_app(state)), fonts=fonts
    )

    async with factory(_spec(tmp_path, tex=False), Listener()) as session:
        await _run_until(session, lambda: state.polls > 0)

    assert calls == []


async def test__session__font_adoption_fails__runner_still_connects(tmp_path: Path) -> None:
    state = FakeRunnerState()

    async def ensure() -> None:
        raise OSError("docker socket gone")

    fonts = SessionFonts(tmp_path / "fonts", str(tmp_path / "fonts"), "/usr/local/share/fonts/hse", ensure)
    factory = runner_session_factory(
        cache_volume="tex-cache", transport=SwitchTransport(create_fake_app(state)), fonts=fonts
    )

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
        '{"api_url": "http://api", "runner_id": "r1", "runner_token": "hsrn_revoked"}', encoding="utf-8", newline="\n"
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


class _FakeOffice:
    """Служба конвертации Студии без Docker: запоминает вызовы и образ, возвращает заданный PDF."""

    def __init__(self, pdf: bytes | None = b"%PDF-1.7 fake") -> None:
        self.pdf = pdf
        self.calls: list[tuple[str, str | None]] = []

    async def convert_to_pdf(self, source: Path, image: str | None = None) -> bytes | None:
        self.calls.append((source.name, image))
        return self.pdf


def _office_spec(data_dir: Path, *, available: bool) -> RunnerSessionSpec:
    return replace(_spec(data_dir), office_available=available, office_image="gotenberg/gotenberg:8-studio")


async def test__session__office_service_available__declares_office_tag(tmp_path: Path) -> None:
    state = FakeRunnerState()
    factory = runner_session_factory(
        cache_volume="tex-cache", transport=SwitchTransport(create_fake_app(state)), office=_FakeOffice()
    )

    async with factory(_office_spec(tmp_path, available=True), Listener()) as session:
        await _run_until(session, lambda: state.polls > 0)

    assert "office" in state.registrations[0]["tags"]


async def test__session__office_service_unavailable__no_office_tag(tmp_path: Path) -> None:
    state = FakeRunnerState()
    factory = runner_session_factory(
        cache_volume="tex-cache", transport=SwitchTransport(create_fake_app(state)), office=_FakeOffice()
    )

    async with factory(_office_spec(tmp_path, available=False), Listener()) as session:
        await _run_until(session, lambda: state.polls > 0)

    assert "office" not in state.registrations[0]["tags"]


async def test__session__no_office_service__no_office_tag_even_if_spec_says_available(tmp_path: Path) -> None:
    state = FakeRunnerState()
    factory = runner_session_factory(cache_volume="tex-cache", transport=SwitchTransport(create_fake_app(state)))

    async with factory(_office_spec(tmp_path, available=True), Listener()) as session:
        await _run_until(session, lambda: state.polls > 0)

    assert "office" not in state.registrations[0]["tags"]


async def test__session__office_job__converts_with_studio_service_and_uploads_pdf(tmp_path: Path) -> None:
    source = b"pptx-bytes"
    digest = hashlib.sha256(source).hexdigest()
    body = envelope_body("office", job_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc")
    body["spec"]["payload"]["source"] = {"path": "deck/slides.pptx", "sha256": digest, "size": len(source)}
    body["spec"]["payload"]["output_path"] = "deck/slides.pdf"
    body["manifest"] = [{"path": "deck/slides.pptx", "sha256": digest, "size": len(source)}]
    state = FakeRunnerState()
    state.blobs[digest] = source
    job = state.enqueue(body)
    office = _FakeOffice(b"%PDF-1.7 converted")
    factory = runner_session_factory(
        cache_volume="tex-cache", transport=SwitchTransport(create_fake_app(state)), office=office
    )

    async with factory(_office_spec(tmp_path, available=True), Listener()) as session:
        await _run_until(session, lambda: job.completed)

    assert job.completed[-1]["result"]["status"] == "succeeded"
    # Образ из задачи сервера не используется: служба запускается с образом самой Студии.
    assert office.calls == [("slides.pptx", "gotenberg/gotenberg:8-studio")]
    assert b"%PDF-1.7 converted" in job.artifacts.values()
