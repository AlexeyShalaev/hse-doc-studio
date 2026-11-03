"""Клиент Kubernetes API: REST на MockTransport, разбор статуса пода и кадров exec, токен из файла."""

from __future__ import annotations

import io
import json
from pathlib import Path

import httpx
import pytest
from hse_doc_studio.infra.compile.k8s.api import KubeApiError
from hse_doc_studio.infra.compile.k8s.client import (
    ExecFrames,
    KubernetesApiClient,
    TokenSource,
    exec_exit_code,
    parse_pod_state,
)


def _client(tmp_path: Path, handler: httpx.MockTransport) -> KubernetesApiClient:
    token = tmp_path / "token"
    token.write_text("sa-token\n", encoding="utf-8")
    return KubernetesApiClient("https://k8s.local:6443", TokenSource(token), tmp_path / "no-ca", transport=handler)


async def test__create_pod__forbidden__api_error_with_status_and_message(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(403, json={"kind": "Status", "message": "pods is forbidden", "reason": "Forbidden"})

    client = _client(tmp_path, httpx.MockTransport(handle))

    with pytest.raises(KubeApiError) as caught:
        await client.create_pod("builds", {"metadata": {"name": "p"}})

    assert caught.value.status == 403
    assert str(caught.value) == "pods is forbidden"
    assert seen[0].url.path == "/api/v1/namespaces/builds/pods"
    assert seen[0].headers["authorization"] == "Bearer sa-token"
    await client.aclose()


async def test__read_pod__missing__none(tmp_path: Path) -> None:
    client = _client(tmp_path, httpx.MockTransport(lambda _r: httpx.Response(404, json={"reason": "NotFound"})))

    assert await client.read_pod("builds", "p") is None


async def test__delete_pod__missing__not_an_error_and_grace_zero(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(404, json={})

    await _client(tmp_path, httpx.MockTransport(handle)).delete_pod("builds", "p")

    assert seen[0].method == "DELETE"
    assert seen[0].url.params["gracePeriodSeconds"] == "0"


async def test__list_pods__selector__names(tmp_path: Path) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.params["labelSelector"] == "a=b"
        return httpx.Response(200, json={"items": [{"metadata": {"name": "x"}}, {"metadata": {"name": "y"}}]})

    assert await _client(tmp_path, httpx.MockTransport(handle)).list_pods("builds", "a=b") == ["x", "y"]


async def test__stream_log__follow_with_timestamps_and_since(tmp_path: Path) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/pods/p/log")
        assert request.url.params["follow"] == "true"
        assert request.url.params["timestamps"] == "true"
        assert request.url.params["sinceTime"] == "2026-11-03T10:00:00Z"
        return httpx.Response(200, content=b"2026-11-03T10:00:00Z a\n2026-11-03T10:00:01Z b\n")

    client = _client(tmp_path, httpx.MockTransport(handle))

    lines = [line async for line in client.stream_log("builds", "p", "tex", "2026-11-03T10:00:00Z")]

    assert lines == ["2026-11-03T10:00:00Z a", "2026-11-03T10:00:01Z b"]


async def test__stream_log__error__api_error(tmp_path: Path) -> None:
    client = _client(tmp_path, httpx.MockTransport(lambda _r: httpx.Response(400, json={"message": "not started"})))

    with pytest.raises(KubeApiError, match="not started"):
        [line async for line in client.stream_log("builds", "p", "tex", None)]


def test__client__no_api_url__config_error(tmp_path: Path) -> None:
    with pytest.raises(KubeApiError, match="api url"):
        KubernetesApiClient("", TokenSource(tmp_path / "t"), tmp_path / "ca")


def test__parse_pod_state__waiting_terminated_and_unschedulable() -> None:
    state = parse_pod_state(
        {
            "status": {
                "phase": "Pending",
                "conditions": [
                    {"type": "PodScheduled", "status": "False", "reason": "Unschedulable", "message": "0/3 nodes"}
                ],
                "containerStatuses": [{"state": {"waiting": {"reason": "ImagePullBackOff", "message": "nope"}}}],
            }
        }
    )

    assert state.phase == "Pending"
    assert state.waiting_reason == "ImagePullBackOff"
    assert state.unschedulable == "0/3 nodes"
    assert state.container_running is False


def test__parse_pod_state__running_container() -> None:
    state = parse_pod_state({"status": {"phase": "Running", "containerStatuses": [{"state": {"running": {}}}]}})

    assert state.container_running is True


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ({"status": "Success"}, 0),
        ({"status": "Failure", "details": {"causes": [{"reason": "ExitCode", "message": "2"}]}}, 2),
        ({"status": "Failure", "message": "container not found"}, -1),
    ],
)
def test__exec_exit_code__status__code(status: dict[str, object], expected: int) -> None:
    assert exec_exit_code(status)[0] == expected


def test__exec_frames__channels__stdout_stderr_and_status() -> None:
    out: list[bytes] = []
    frames = ExecFrames(out.append)

    frames.feed(b"\x01hello")
    frames.feed(b"\x02warn")
    frames.feed(b"")
    frames.feed(b"\x03" + json.dumps({"status": "Success"}).encode())

    result = frames.result("p")
    assert out == [b"hello"]
    assert result.exit_code == 0
    assert result.stderr == "warn"


def test__exec_frames__no_status__error() -> None:
    with pytest.raises(KubeApiError, match="without status"):
        ExecFrames(None).result("p")


def test__token_source__rotated_file__reread_after_ttl(tmp_path: Path) -> None:
    path = tmp_path / "token"
    path.write_text("one", encoding="utf-8")
    source = TokenSource(path, ttl_s=0)
    assert source.get() == "one"

    path.write_text("two", encoding="utf-8")

    assert source.get() == "two"


def test__token_source__missing_file__api_error(tmp_path: Path) -> None:
    with pytest.raises(KubeApiError, match="token"):
        TokenSource(tmp_path / "missing").get()


async def test__exec__websocket__stdin_frames_in_stdout_and_exit_code_out(tmp_path: Path) -> None:
    pytest.importorskip("websockets")
    from websockets.asyncio.server import ServerConnection, serve  # noqa: PLC0415
    from websockets.typing import Subprotocol  # noqa: PLC0415

    received = bytearray()
    seen: dict[str, object] = {}

    async def handler(conn: ServerConnection) -> None:
        seen["path"] = conn.request.path if conn.request else ""
        seen["auth"] = conn.request.headers.get("Authorization") if conn.request else ""
        seen["subprotocol"] = conn.subprotocol
        while len(received) < 100_000:
            frame = await conn.recv()
            assert isinstance(frame, bytes)
            assert frame[0] == 0
            received.extend(frame[1:])
        await conn.send(b"\x01" + b"done")
        status = {"status": "Failure", "details": {"causes": [{"reason": "ExitCode", "message": "3"}]}}
        await conn.send(b"\x03" + json.dumps(status).encode())

    async with serve(handler, "127.0.0.1", 0, subprotocols=[Subprotocol("v4.channel.k8s.io")]) as server:
        port = server.sockets[0].getsockname()[1]
        token = tmp_path / "token"
        token.write_text("sa", encoding="utf-8")
        client = KubernetesApiClient(f"http://127.0.0.1:{port}", TokenSource(token), tmp_path / "ca")
        out: list[bytes] = []

        result = await client.exec(
            "builds",
            "p",
            "tex",
            ["sh", "-c", "head -c 100000 | tar -x"],
            stdin=io.BytesIO(b"x" * 100_000),
            stdout=out.append,
        )
        await client.aclose()

    assert bytes(received) == b"x" * 100_000
    assert out == [b"done"]
    assert result.exit_code == 3
    assert seen["subprotocol"] == "v4.channel.k8s.io"
    assert seen["auth"] == "Bearer sa"
    path = str(seen["path"])
    assert path.startswith("/api/v1/namespaces/builds/pods/p/exec?")
    assert "command=sh&command=-c" in path
    assert "stdin=true" in path


async def test__exec__http_rejected__api_error_with_status(tmp_path: Path) -> None:
    pytest.importorskip("websockets")
    from websockets.asyncio.server import ServerConnection, serve  # noqa: PLC0415
    from websockets.http11 import Request, Response  # noqa: PLC0415

    def reject(conn: ServerConnection, request: Request) -> Response:
        return conn.respond(403, "forbidden\n")

    async def handler(conn: ServerConnection) -> None:
        return None

    async with serve(handler, "127.0.0.1", 0, process_request=reject) as server:
        port = server.sockets[0].getsockname()[1]
        token = tmp_path / "token"
        token.write_text("sa", encoding="utf-8")
        client = KubernetesApiClient(f"http://127.0.0.1:{port}", TokenSource(token), tmp_path / "ca")

        with pytest.raises(KubeApiError) as caught:
            await client.exec("builds", "p", "tex", ["true"])
        await client.aclose()

    assert caught.value.status == 403
