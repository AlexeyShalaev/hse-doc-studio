"""Мягкая остановка api: ожидающие запросы получают 503 с Retry-After, потоки событий закрываются сразу.

Без звена uvicorn по истечении `timeout_graceful_shutdown` отменял запрос и отвечал голым 500: так MCP
`compile_document` ответил «Internal Server Error» во время выкатки 08.11.2026.
"""

from __future__ import annotations

import asyncio
import json
import signal
from typing import Any

import pytest
from hse_doc_studio.api.graceful_shutdown import GracefulShutdownMiddleware, _hook_signals
from hse_doc_studio.core.shutdown import ShutdownSignal
from starlette.types import Message, Receive, Scope, Send


def _scope(path: str = "/mcp", headers: list[tuple[bytes, bytes]] | None = None) -> Scope:
    return {"type": "http", "method": "POST", "path": path, "headers": headers or []}


class Exchange:
    def __init__(self) -> None:
        self.sent: list[Message] = []

    async def receive(self) -> Message:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def send(self, message: Message) -> None:
        self.sent.append(message)

    @property
    def status(self) -> int | None:
        start = next((m for m in self.sent if m["type"] == "http.response.start"), None)
        return None if start is None else int(start["status"])

    @property
    def headers(self) -> dict[str, str]:
        start = next(m for m in self.sent if m["type"] == "http.response.start")
        return {k.decode(): v.decode() for k, v in start["headers"]}

    @property
    def body(self) -> bytes:
        return b"".join(m.get("body", b"") for m in self.sent if m["type"] == "http.response.body")

    @property
    def completed(self) -> bool:
        return any(m["type"] == "http.response.body" and not m.get("more_body", False) for m in self.sent)


async def _hanging(scope: Scope, receive: Receive, send: Send) -> None:
    """Долгое ожидание без начатого ответа: как `compile_document`, ждущий сборку."""
    await asyncio.sleep(3600)


async def _event_stream(scope: Scope, receive: Receive, send: Send) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/event-stream")]})
    await send({"type": "http.response.body", "body": b"event: log\ndata: x\n\n", "more_body": True})
    await asyncio.sleep(3600)


async def _ok(scope: Scope, receive: Receive, send: Send) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
    await send({"type": "http.response.body", "body": b"ok"})


async def _run(middleware: GracefulShutdownMiddleware, scope: Scope, exchange: Exchange) -> asyncio.Task[None]:
    task = asyncio.create_task(middleware(scope, exchange.receive, exchange.send))
    await asyncio.sleep(0.01)
    return task


async def test__request_without_shutdown__passes_through_untouched() -> None:
    middleware = GracefulShutdownMiddleware(_ok, shutdown=ShutdownSignal(), grace_s=0.05)
    exchange = Exchange()

    await middleware(_scope(), exchange.receive, exchange.send)

    assert (exchange.status, exchange.body) == (200, b"ok")


async def test__new_request_after_signal__503_server_restarting_with_retry_after() -> None:
    shutdown = ShutdownSignal()
    shutdown.request()
    middleware = GracefulShutdownMiddleware(_ok, shutdown=shutdown, grace_s=0.05, retry_after_s=30)
    exchange = Exchange()

    await middleware(_scope(headers=[(b"accept-language", b"en-US,en")]), exchange.receive, exchange.send)

    assert exchange.status == 503
    assert exchange.headers["retry-after"] == "30"
    body = json.loads(exchange.body)
    assert body["code"] == "server_restarting"
    assert "restarting" in body["detail"]


async def test__pending_request_at_grace_deadline__503_instead_of_uvicorn_500() -> None:
    shutdown = ShutdownSignal()
    middleware = GracefulShutdownMiddleware(_hanging, shutdown=shutdown, grace_s=0.05)
    exchange = Exchange()
    task = await _run(middleware, _scope(), exchange)

    shutdown.request()
    async with asyncio.timeout(2):
        await task

    assert not task.cancelled()
    assert exchange.status == 503
    assert json.loads(exchange.body)["code"] == "server_restarting"
    assert exchange.headers["retry-after"]
    assert "перезапускается" in json.loads(exchange.body)["detail"]


async def test__cancelled_by_the_server_after_signal__still_answers_503() -> None:
    """uvicorn сам отменяет запрос по сроку: звено ловит и эту отмену."""
    shutdown = ShutdownSignal()
    middleware = GracefulShutdownMiddleware(_hanging, shutdown=shutdown, grace_s=60)
    exchange = Exchange()
    task = await _run(middleware, _scope(), exchange)

    shutdown.request()
    task.cancel()
    async with asyncio.timeout(2):
        await task

    assert exchange.status == 503


async def test__event_stream__closed_at_once_on_signal_not_after_grace() -> None:
    shutdown = ShutdownSignal()
    middleware = GracefulShutdownMiddleware(_event_stream, shutdown=shutdown, grace_s=60)
    exchange = Exchange()
    task = await _run(middleware, _scope("/api/v1/stream"), exchange)

    shutdown.request()
    async with asyncio.timeout(2):
        await task

    assert exchange.status == 200
    assert exchange.completed


async def test__cancel_without_shutdown__propagates() -> None:
    middleware = GracefulShutdownMiddleware(_hanging, shutdown=ShutdownSignal(), grace_s=0.05)
    exchange = Exchange()
    task = await _run(middleware, _scope(), exchange)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert exchange.sent == []


def test__signal_hook__raises_the_flag_and_calls_the_server_handler() -> None:
    shutdown = ShutdownSignal()
    seen: list[int] = []
    original = signal.getsignal(signal.SIGTERM)

    def server_handler(signum: int, frame: Any) -> None:
        seen.append(signum)

    signal.signal(signal.SIGTERM, server_handler)
    try:
        previous = _hook_signals(shutdown)
        handler = signal.getsignal(signal.SIGTERM)
        assert callable(handler)
        handler(signal.SIGTERM, None)
    finally:
        signal.signal(signal.SIGTERM, original)
        for sig, prev in previous.items():
            if sig != signal.SIGTERM:
                signal.signal(sig, prev)

    assert shutdown.requested
    assert seen == [signal.SIGTERM]
    assert previous[signal.SIGTERM] is server_handler


async def test__shutdown_signal__wakes_waiters_and_times_out_without_it() -> None:
    shutdown = ShutdownSignal()
    assert await shutdown.wait_for(0.01) is False

    waiter = asyncio.create_task(shutdown.wait_for(5))
    await asyncio.sleep(0)
    shutdown.request()

    async with asyncio.timeout(1):
        assert await waiter is True
