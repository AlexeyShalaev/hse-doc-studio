"""Поддельный OpenAI-совместимый сервер для ретрансляции: режимы «медленно», «обрыв», «500», «огромный ответ»."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx

MODELS = {"object": "list", "data": [{"id": "fake-model", "object": "model"}]}


def sse_chunks(tokens: list[str]) -> list[bytes]:
    chunks = [
        f"data: {json.dumps({'choices': [{'index': 0, 'delta': {'content': token}}]})}\n\n".encode() for token in tokens
    ]
    return [*chunks, b"data: [DONE]\n\n"]


class _Stream(httpx.AsyncByteStream):
    def __init__(self, server: FakeOpenAI, chunks: list[bytes], delay_s: float) -> None:
        self._server = server
        self._chunks = chunks
        self._delay_s = delay_s

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            if self._delay_s:
                await asyncio.sleep(self._delay_s)
            yield chunk
            self._server.sent_chunks += 1

    async def aclose(self) -> None:
        self._server.closed += 1


@dataclass
class FakeOpenAI:
    """`mode`: ok, slow, down, error500, huge, redirect, hang (заголовка нет)."""

    mode: str = "ok"
    tokens: list[str] = field(default_factory=lambda: ["Привет", ", ", "мир"])
    delay_s: float = 0.2
    requests: list[httpx.Request] = field(default_factory=list)
    bodies: list[bytes] = field(default_factory=list)
    closed: int = 0
    sent_chunks: int = 0

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    async def _handle(self, request: httpx.Request) -> httpx.Response:  # noqa: C901 — по ветке на режим
        self.requests.append(request)
        self.bodies.append(await request.aread())
        if self.mode == "down":
            raise httpx.ConnectError("connection refused", request=request)
        if self.mode == "hang":
            await asyncio.sleep(30)
        if request.url.path.endswith("/models"):
            return self._json(200, MODELS)
        if self.mode == "error500":
            return self._json(500, {"error": {"message": "boom"}})
        if self.mode == "redirect":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest"})
        chunks = sse_chunks(self.tokens)
        if self.mode == "plain":
            text = "".join(self.tokens)
            return self._json(200, {"choices": [{"index": 0, "message": {"role": "assistant", "content": text}}]})
        if self.mode == "huge":
            chunks = [b"x" * 40_000 for _ in range(10)]
        delay = self.delay_s if self.mode == "slow" else 0.0
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=_Stream(self, chunks, delay))

    def _json(self, status: int, body: object) -> httpx.Response:
        # Потоком, как настоящий сервер: MockTransport иначе отдаёт уже прочитанное тело.
        raw = json.dumps(body).encode()
        return httpx.Response(status, headers={"content-type": "application/json"}, stream=_Stream(self, [raw], 0.0))
