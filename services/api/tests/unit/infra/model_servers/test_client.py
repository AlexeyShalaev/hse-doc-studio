"""HTTP к движкам на подменённом транспорте."""

from __future__ import annotations

import json

import httpx
from hse_doc_studio.core.model_servers import Engine
from hse_doc_studio.infra.model_servers.client import HttpModelServerClient

BASE = "http://engine:1"


def _client(handler) -> HttpModelServerClient:  # type: ignore[no-untyped-def]
    return HttpModelServerClient(httpx.MockTransport(handler))


async def test_pull_stream_reports_percent_then_done() -> None:
    lines = [
        {"status": "pulling manifest"},
        {"status": "downloading", "total": 200, "completed": 50},
        {"status": "success"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/pull"
        return httpx.Response(200, content="\n".join(json.dumps(x) for x in lines))

    events = [e async for e in _client(handler).pull(BASE, "qwen3:4b")]
    assert [e.percent for e in events] == [None, 25, 100]
    assert events[-1].done


async def test_pull_error_event() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps({"error": "pull model manifest: file does not exist"}))

    events = [e async for e in _client(handler).pull(BASE, "nope")]
    assert events[0].error is not None


async def test_ping_sends_key_and_reports_status() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={})

    assert await _client(handler).ping(BASE, "m", "KEY")
    assert seen["auth"] == "Bearer KEY"
    assert not await _client(lambda _: httpx.Response(500)).ping(BASE, "m")


async def test_installed_models_per_engine() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "a:1"}]})
        return httpx.Response(200, json={"data": [{"id": "org/b"}]})

    c = _client(handler)
    assert await c.installed_models(Engine.ollama, BASE) == ["a:1"]
    assert await c.installed_models(Engine.vllm, BASE) == ["org/b"]
    assert await _client(lambda _: httpx.Response(200, content=b"x")).installed_models(Engine.vllm, BASE) == []
