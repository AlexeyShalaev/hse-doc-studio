"""HTTP-транспорт OpenAI SDK для провайдера «через мой раннер»: вместо соединения с моделью задача `ai.relay`.

SDK строится как обычно, но с этим транспортом и фиктивным базовым адресом: транспорт не открывает соединений,
он берёт путь после `/v1`, метод и тело и отдаёт их `AiRelayClient`. Ответ раннера возвращается SDK обычным
потоковым HTTP-ответом, поэтому чат стримит токены так же, как с прямым провайдером. Ошибка ретрансляции
пробрасывается транспортной ошибкой httpx с `AiRelayError` в `__cause__` (её достаёт `relay_error_of`).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import UUID

import httpx2

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.jobs.relay import RelayErrorCode, RelayMethod, RelayPath, is_relay_route
from hse_doc_studio.use_cases.ai_relay.client import (
    AiRelayClient,
    AiRelayError,
    AiRelayTimeoutError,
    RelayRequest,
    RelayResponse,
)

# Хост, которого нет: SDK требует базовый адрес, а соединение транспорт всё равно не открывает.
RELAY_BASE_URL = "http://runner-relay.invalid/v1"
_PREFIX = "/v1/"


class _RelayStream(httpx2.AsyncByteStream):
    def __init__(self, response: RelayResponse, opened: set[RelayResponse]) -> None:
        self._response = response
        self._opened = opened

    async def __aiter__(self) -> AsyncIterator[bytes]:
        try:
            async for chunk in self._response.aiter_bytes():
                yield chunk
        except AiRelayTimeoutError as exc:
            raise httpx2.ReadTimeout(str(exc)) from exc
        except AiRelayError as exc:
            raise httpx2.RemoteProtocolError(str(exc)) from exc

    async def aclose(self) -> None:
        # Закрытие до конца ответа (отмена чата, обрыв SSE клиента) отменяет задачу на раннере.
        self._opened.discard(self._response)
        await self._response.aclose()


class RunnerRelayTransport(httpx2.AsyncBaseTransport):
    def __init__(self, client: AiRelayClient, actor: Actor, provider: AIProvider, project_id: UUID | None) -> None:
        if provider.runner_id is None or provider.runner_endpoint is None:
            raise ValueError("provider is not a runner provider")
        self._client = client
        self._actor = actor
        self._provider = provider
        self._project_id = project_id
        # Ответы, которые SDK ещё не закрыл: закрытие клиента (отмена задачи asyncio посреди чтения) закрывает и их.
        self._opened: set[RelayResponse] = set()

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        relay_path = path[len(_PREFIX) :] if path.startswith(_PREFIX) else path.lstrip("/")
        if request.url.query or not is_relay_route(request.method, relay_path):
            error = AiRelayError(RelayErrorCode.path_forbidden, reason=f"{request.method} {relay_path}")
            raise httpx2.UnsupportedProtocol(str(error), request=request) from error
        body = await request.aread()
        timeout_s = self._provider.request_timeout_s
        relay_request = RelayRequest(
            runner_id=self._provider.runner_id or "",
            endpoint=self._provider.runner_endpoint or "",
            path=RelayPath(relay_path),
            method=RelayMethod(request.method),
            body=body,
            content_type=request.headers.get("content-type") if body else None,
            stream=_wants_stream(body),
            head_timeout_s=timeout_s,
            idle_timeout_s=timeout_s,
            project_id=self._project_id,
        )
        try:
            response = await self._client.open(self._actor, relay_request)
        except AiRelayTimeoutError as exc:
            raise httpx2.ReadTimeout(str(exc), request=request) from exc
        except AiRelayError as exc:
            raise httpx2.ConnectError(str(exc), request=request) from exc
        headers = {"content-type": response.content_type} if response.content_type else {}
        self._opened.add(response)
        return httpx2.Response(
            response.status_code, headers=headers, stream=_RelayStream(response, self._opened), request=request
        )

    async def aclose(self) -> None:
        opened, self._opened = list(self._opened), set()
        for response in opened:
            await response.aclose()


def _wants_stream(body: bytes) -> bool:
    if not body:
        return False
    try:
        parsed = json.loads(body)
    except ValueError:
        return False
    return isinstance(parsed, dict) and parsed.get("stream") is True
