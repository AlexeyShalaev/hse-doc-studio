"""Транспорт OpenAI SDK через ретрансляцию: брошенный ответ закрывается вместе с клиентом."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import httpx2
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderType
from hse_doc_studio.infra.ai.relay_transport import RELAY_BASE_URL, RunnerRelayTransport
from hse_doc_studio.use_cases.ai_relay.client import RelayRequest

_ANNA = Actor.user("0a0a0a0a-0000-4000-8000-000000000000", "Анна")
_PROVIDER = AIProvider(
    id=UUID(int=1),
    name="Ollama на ноутбуке",
    type=AIProviderType.runner,
    api_key="",
    base_url="",
    models=[],
    created_at=datetime(2026, 10, 30, tzinfo=UTC),
    runner_id="4f1c2b3a5d6e47f89a0b1c2d3e4f5a6b",
    runner_endpoint="ollama",
)


class _Response:
    status_code = 200
    content_type = "text/event-stream"

    def __init__(self) -> None:
        self.closed = 0

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        yield b"data: {}\n\n"

    async def aclose(self) -> None:
        self.closed += 1


class _Relay:
    def __init__(self) -> None:
        self.requests: list[RelayRequest] = []
        self.responses: list[_Response] = []

    async def open(self, _actor: Actor, request: RelayRequest) -> _Response:
        self.requests.append(request)
        response = _Response()
        self.responses.append(response)
        return response


def _client(relay: _Relay, project_id: UUID | None = None) -> httpx2.AsyncClient:
    transport = RunnerRelayTransport(relay, _ANNA, _PROVIDER, project_id)  # type: ignore[arg-type]
    return httpx2.AsyncClient(transport=transport, base_url=RELAY_BASE_URL)


async def test__aclose__abandoned_response__closed_with_the_client() -> None:
    relay = _Relay()
    client = _client(relay)
    request = client.build_request("POST", "/chat/completions", json={"model": "qwen", "stream": True})

    await client.send(request, stream=True)  # тело не читаем и не закрываем, как при отмене посреди чтения
    await client.aclose()

    assert [response.closed for response in relay.responses] == [1]


async def test__aclose__response_closed_by_the_reader__not_closed_twice() -> None:
    relay = _Relay()
    client = _client(relay)

    async with client.stream("POST", "/chat/completions", json={"model": "qwen", "stream": True}) as response:
        await response.aread()
    await client.aclose()

    assert [response.closed for response in relay.responses] == [1]
