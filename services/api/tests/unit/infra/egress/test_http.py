from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpcore
import pytest
from hse_doc_studio.core.egress import EgressBlockedError
from hse_doc_studio.infra.egress.http import PinningBackend, egress_client
from hse_doc_studio.infra.egress.policy import ResolvingEgressPolicy


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 — имя задаёт http.server
        if self.path == "/to-private":
            self.send_response(302)
            self.send_header("Location", "http://10.0.0.5/secret")
            self.send_header("Content-Length", "0")
        elif self.path == "/to-metadata":
            self.send_response(302)
            self.send_header("Location", "http://169.254.169.254/latest/meta-data/")
            self.send_header("Content-Length", "0")
        else:
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")
            return
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


@pytest.fixture
def local_server() -> Iterator[int]:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    thread.join()


async def test__request_to_loopback__blocked(local_server: int) -> None:
    async with egress_client(ResolvingEgressPolicy()) as client:
        with pytest.raises(EgressBlockedError):
            await client.get(f"http://127.0.0.1:{local_server}/")


async def test__request_to_metadata_address__blocked() -> None:
    async with egress_client(ResolvingEgressPolicy()) as client:
        with pytest.raises(EgressBlockedError):
            await client.get("http://169.254.169.254/latest/meta-data/")


async def test__allowlisted_loopback__reachable(local_server: int) -> None:
    async with egress_client(ResolvingEgressPolicy(["127.0.0.1"])) as client:
        response = await client.get(f"http://127.0.0.1:{local_server}/")

    assert response.text == "ok"


async def test__redirect_to_private__blocked_on_the_hop(local_server: int) -> None:
    async with egress_client(ResolvingEgressPolicy(["127.0.0.1"]), follow_redirects=True) as client:
        with pytest.raises(EgressBlockedError):
            await client.get(f"http://127.0.0.1:{local_server}/to-private")


async def test__redirect_to_metadata__blocked_even_with_allowlisted_origin(local_server: int) -> None:
    async with egress_client(ResolvingEgressPolicy(["127.0.0.1", "169.254.0.0/16"]), follow_redirects=True) as client:
        with pytest.raises(EgressBlockedError):
            await client.get(f"http://127.0.0.1:{local_server}/to-metadata")


async def test__redirect_not_followed_by_default__client_sees_the_302(local_server: int) -> None:
    async with egress_client(ResolvingEgressPolicy(["127.0.0.1"])) as client:
        response = await client.get(f"http://127.0.0.1:{local_server}/to-private")

    assert response.status_code == 302


class _RecordingBackend(httpcore.AsyncNetworkBackend):
    def __init__(self) -> None:
        self.connected: list[tuple[str, int]] = []

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):  # type: ignore[no-untyped-def]
        self.connected.append((host, port))
        raise httpcore.ConnectError("stop")

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):  # type: ignore[no-untyped-def]
        raise httpcore.ConnectError("stop")

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


async def test__connection__goes_to_the_checked_ip_not_to_the_name() -> None:
    answers = {"git.example.org": ["93.184.216.34"]}

    async def resolve(host: str, port: int) -> list[str]:
        return answers[host]

    backend = _RecordingBackend()
    pinning = PinningBackend(ResolvingEgressPolicy(resolver=resolve), "user", backend)  # type: ignore[arg-type]

    with pytest.raises(httpcore.ConnectError):
        await pinning.connect_tcp("git.example.org", 443)

    assert backend.connected == [("93.184.216.34", 443)]
