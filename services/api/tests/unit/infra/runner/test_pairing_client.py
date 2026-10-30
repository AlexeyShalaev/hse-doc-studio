from __future__ import annotations

import httpx
import pytest
from hse_doc_studio.infra.runner.client import RunnerApiError, RunnerUnreachable
from hse_doc_studio.infra.runner.pairing_client import PairingStatus, RunnerPairingClient, is_disabled

from tests.unit.infra.remote_runner.fake_pairing_api import DEVICE_CODE, PAIRED_TOKEN, USER_CODE, FakePairingServer

_URL = "https://studio.example.org"


def _client(server: FakePairingServer) -> RunnerPairingClient:
    return RunnerPairingClient(_URL, version="0.3.0", transport=server.transport())


async def test__start__returns_codes_and_sends_name_and_kind() -> None:
    server = FakePairingServer()
    client = _client(server)

    started = await client.start("MacBook Анны", "desktop")

    assert (started.device_code, started.user_code) == (DEVICE_CODE, USER_CODE)
    assert started.verification_uri_complete.endswith(f"?code={USER_CODE}")
    assert server.starts == [{"name": "MacBook Анны", "host_kind": "desktop"}]
    await client.aclose()


async def test__poll__approved_once__then_expired() -> None:
    server = FakePairingServer(statuses=["approved"])
    client = _client(server)

    first = await client.poll(DEVICE_CODE)
    second = await client.poll(DEVICE_CODE)

    assert (first.status, first.registration_token) == (PairingStatus.approved, PAIRED_TOKEN)
    assert (second.status, second.registration_token) == (PairingStatus.expired, None)
    await client.aclose()


async def test__start__runner_disabled__raises_api_error_with_code() -> None:
    client = _client(FakePairingServer(start_error=(403, "runner_disabled")))

    with pytest.raises(RunnerApiError) as caught:
        await client.start("x", "desktop")

    assert is_disabled(caught.value)
    await client.aclose()


async def test__start__connection_refused__raises_unreachable() -> None:
    client = _client(FakePairingServer(unreachable=True))

    with pytest.raises(RunnerUnreachable):
        await client.start("x", "desktop")
    await client.aclose()


async def test__poll__unexpected_field__is_rejected() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "pending", "registration_token": None, "extra": 1})

    client = RunnerPairingClient(_URL, version="0.3.0", transport=httpx.MockTransport(handler))

    with pytest.raises(RunnerApiError):
        await client.poll(DEVICE_CODE)
    await client.aclose()


async def test__deregister__sends_runner_token_and_id() -> None:
    server = FakePairingServer()
    client = _client(server)

    await client.deregister("runner-1", "hsrn_secret")

    assert server.deregistered == [("runner-1", "hsrn_secret")]
    await client.aclose()


def _start_answer(uri: str, complete: str) -> httpx.MockTransport:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "device_code": DEVICE_CODE,
                "user_code": USER_CODE,
                "verification_uri": uri,
                "verification_uri_complete": complete,
                "expires_in": 600,
                "interval": 5,
            },
        )

    return httpx.MockTransport(handler)


@pytest.mark.parametrize(
    "complete",
    [
        "javascript:alert(1)",
        "http://studio.example.org/settings/runners/pair?code=X",
        "https://evil.example.org/settings/runners/pair?code=X",
        "https://studio.example.org:8443/settings/runners/pair?code=X",
        "/settings/runners/pair?code=X",
    ],
)
async def test__start__verification_uri_off_server__is_rejected(complete: str) -> None:
    uri = f"{_URL}/settings/runners/pair"
    client = RunnerPairingClient(_URL, version="0.3.0", transport=_start_answer(uri, complete))

    with pytest.raises(RunnerApiError, match="verification_uri_complete"):
        await client.start("x", "desktop")
    await client.aclose()


async def test__start__verification_uri_same_server_with_default_port__accepted() -> None:
    uri = "https://STUDIO.example.org:443/settings/runners/pair"
    client = RunnerPairingClient(_URL + "/prefix", version="0.3.0", transport=_start_answer(uri, uri + "?code=X"))

    started = await client.start("x", "desktop")

    assert started.verification_uri_complete == uri + "?code=X"
    await client.aclose()
