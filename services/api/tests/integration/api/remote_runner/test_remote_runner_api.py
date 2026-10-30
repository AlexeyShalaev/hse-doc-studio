from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import pytest_asyncio
from hse_doc_studio.api.schemas.remote_runner import RemoteRunnerStatus
from hse_doc_studio.infra.remote_runner.settings_store import JsonRemoteRunnerSettingsStore
from hse_doc_studio.infra.remote_runner.supervisor import RemoteRunnerSupervisor
from hse_doc_studio.infra.runner.pairing_client import RunnerPairingClient
from httpx import ASGITransport, AsyncClient

from tests.fixtures.app import create_test_app, create_test_container
from tests.unit.infra.remote_runner.fake_pairing_api import USER_CODE, FakePairingServer
from tests.unit.infra.remote_runner.fakes import FakeSessions, eventually

_URL = "https://studio.example.org"
_BASE = "/api/v1/remote-runner"


@dataclass
class Env:
    client: AsyncClient
    server: FakePairingServer
    sessions: FakeSessions
    supervisor: RemoteRunnerSupervisor


@pytest_asyncio.fixture
async def env(tmp_path: Path) -> AsyncIterator[Env]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    server = FakePairingServer()
    sessions = FakeSessions()
    supervisor = RemoteRunnerSupervisor(
        JsonRemoteRunnerSettingsStore(data_dir),
        runner_dir=data_dir / "remote-runner",
        default_name="studio-mac",
        pairing_client=lambda url: RunnerPairingClient(url, version="0.3.0", transport=server.transport()),
        session_factory=sessions,
        min_pairing_interval_s=0.0,
    )
    await supervisor.start()
    container = create_test_container(data_dir, remote_runner=supervisor)
    async with AsyncClient(transport=ASGITransport(app=create_test_app(container)), base_url="http://test") as client:
        yield Env(client, server, sessions, supervisor)
    await supervisor.stop()
    await container.close()


async def _status(client: AsyncClient) -> dict[str, object]:
    resp = await client.get(_BASE)
    assert resp.status_code == 200, resp.text
    # Ответ строго совпадает с контрактом: лишнее поле уронит разбор.
    return RemoteRunnerStatus.model_validate(resp.json()).model_dump(mode="json")


async def test__get__fresh_install__off_and_not_paired(env: Env) -> None:
    status = await _status(env.client)

    assert (status["state"], status["enabled"], status["paired"]) == ("off", False, False)
    assert status["pairing"] is None


async def test__put__enable_with_server__unpaired_with_default_name(env: Env) -> None:
    resp = await env.client.put(_BASE, json={"enabled": True, "server_url": _URL + "/"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["state"], body["server_url"], body["runner_name"]) == ("unpaired", _URL, "studio-mac")


async def test__put__concurrency_out_of_range__422(env: Env) -> None:
    resp = await env.client.put(_BASE, json={"concurrency": 9})

    assert resp.status_code == 422


async def test__put__duplicate_endpoint_names__422(env: Env) -> None:
    choice = {"name": "ollama", "provider_id": "p1"}
    resp = await env.client.put(_BASE, json={"ai_endpoints": [choice, {**choice, "provider_id": "p2"}]})

    assert resp.status_code == 422
    assert resp.json()["code"] == "input_invalid"


async def test__pair__approved__reaches_online(env: Env) -> None:
    resp = await env.client.post(f"{_BASE}/pair", json={"server_url": _URL, "name": "MacBook Анны"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] in {"pairing", "connecting", "online"}
    if body["state"] == "pairing":
        assert body["pairing"]["user_code"] == USER_CODE
    await eventually(lambda: env.supervisor.status().state.value == "online")
    status = await _status(env.client)
    assert (status["paired"], status["runner_name"], status["enabled"]) == (True, "MacBook Анны", True)


@pytest.mark.parametrize(
    ("server_url", "code"),
    [("http://studio.example.org", "remote_runner_url_invalid"), ("studio", "remote_runner_url_invalid")],
)
async def test__pair__bad_address__422_with_code(env: Env, server_url: str, code: str) -> None:
    resp = await env.client.post(f"{_BASE}/pair", json={"server_url": server_url, "name": "Mac"})

    assert resp.status_code == 422
    assert resp.json()["code"] == code


async def test__pair__personal_runners_off_on_server__409_disabled(env: Env) -> None:
    env.server.start_error = (403, "runner_disabled")

    resp = await env.client.post(f"{_BASE}/pair", json={"server_url": _URL, "name": "Mac"})

    assert resp.status_code == 409
    assert resp.json()["code"] == "remote_runner_disabled"


async def test__pair__server_down__502_unreachable(env: Env) -> None:
    env.server.unreachable = True

    resp = await env.client.post(f"{_BASE}/pair", json={"server_url": _URL, "name": "Mac"})

    assert resp.status_code == 502
    assert resp.json()["code"] == "remote_runner_unreachable"


async def test__cancel_pairing__back_to_unpaired(env: Env) -> None:
    env.server.statuses = ["pending"]
    await env.client.post(f"{_BASE}/pair", json={"server_url": _URL, "name": "Mac"})

    resp = await env.client.delete(f"{_BASE}/pairing")

    assert resp.status_code == 200
    assert (resp.json()["state"], resp.json()["pairing"]) == ("unpaired", None)


async def test__token__valid__starts_session(env: Env) -> None:
    token = "hsrt_Q2xvdWRSdW5uZXJUb2tlbkV4YW1wbGUx"  # noqa: S105 — значение эталона

    resp = await env.client.post(f"{_BASE}/token", json={"server_url": _URL, "token": token})

    assert resp.status_code == 200, resp.text
    await eventually(lambda: len(env.sessions.specs) == 1)
    assert env.sessions.specs[0].registration_token == token


async def test__token__malformed__422_without_echoing_secret(env: Env) -> None:
    resp = await env.client.post(f"{_BASE}/token", json={"server_url": _URL, "token": "not-a-token-secret"})

    assert resp.status_code == 422
    assert "not-a-token-secret" not in resp.text


async def test__delete__paired__deregisters_and_turns_off(env: Env) -> None:
    await env.client.post(f"{_BASE}/pair", json={"server_url": _URL, "name": "Mac"})
    await eventually(lambda: env.supervisor.status().paired)

    resp = await env.client.delete(_BASE)

    assert resp.status_code == 200
    body = resp.json()
    assert (body["state"], body["paired"], body["enabled"]) == ("off", False, False)
    assert len(env.server.deregistered) == 1
