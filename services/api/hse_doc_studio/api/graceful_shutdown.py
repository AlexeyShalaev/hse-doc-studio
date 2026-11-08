"""Мягкая остановка api: ожидающие запросы получают ответ, а не 500 от uvicorn.

По SIGTERM uvicorn закрывает порт и ждёт идущие запросы `timeout_graceful_shutdown` секунд, потом отменяет их.
Отменённый запрос без начатого ответа uvicorn закрывает голым «500 Internal Server Error»: так MCP
`compile_document` и отвечал во время выкатки. А потоки событий (SSE вкладки «Сборка») держали остановку все
десять секунд, на которые и растягивалось окно недоступности.

Здесь три части:
- обработчик сигнала поднимает `process_shutdown()` в момент SIGTERM/SIGINT, раньше, чем uvicorn начнёт ждать
  соединения (события `shutdown` приложения идут уже после этого ожидания);
- промежуточное звено закрывает потоки событий сразу, а ответы, не начатые за `grace_s`, отменяет само и
  отвечает 503 `server_restarting` с `Retry-After`; отмену от uvicorn по истечении срока оно ловит так же;
- новый запрос, пришедший по живому keep-alive соединению после сигнала, сразу получает тот же 503.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
import threading
from collections.abc import Callable
from types import FrameType
from typing import Any

import structlog
from fastapi import FastAPI
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from hse_doc_studio.core.shutdown import RESTART_RETRY_AFTER_S, ShutdownSignal, process_shutdown

logger = structlog.get_logger(__name__)

SERVER_RESTARTING_CODE = "server_restarting"
_EVENT_STREAM = b"text/event-stream"
_HANDLED_SIGNALS = (signal.SIGTERM, signal.SIGINT)
# Запас до срока uvicorn: свой 503 успевает уйти раньше, чем uvicorn отменит запрос и ответит 500.
_GRACE_MARGIN_S = 2.0

_MESSAGES = {
    "ru": "Сервер Студии перезапускается. Повторите запрос через {s} с.",
    "en": "The Studio server is restarting. Retry in {s} s.",
}


def _language(scope: Scope) -> str:
    headers = dict(scope.get("headers") or [])
    explicit = headers.get(b"x-interface-language", b"").decode("latin-1").strip().lower()
    if explicit in _MESSAGES:
        return explicit
    accept = headers.get(b"accept-language", b"").decode("latin-1").strip().lower()
    return "en" if accept.startswith("en") else "ru"


def restarting_response(scope: Scope, retry_after_s: int = RESTART_RETRY_AFTER_S) -> JSONResponse:
    """503 `server_restarting`: тело как у остальных отказов api (`detail`, `code`) и `Retry-After`."""
    detail = _MESSAGES[_language(scope)].format(s=retry_after_s)
    return JSONResponse(
        {"detail": detail, "code": SERVER_RESTARTING_CODE},
        status_code=503,
        headers={"Retry-After": str(retry_after_s), "Cache-Control": "no-store"},
    )


class _Call:
    """Идущий запрос: его задача и что из ответа уже ушло клиенту."""

    __slots__ = ("completed", "started", "streaming", "task")

    def __init__(self, task: asyncio.Task[Any]) -> None:
        self.task = task
        self.started = False
        self.streaming = False
        self.completed = False

    def observe(self, message: Message) -> None:
        if message["type"] == "http.response.start":
            self.started = True
            headers = message.get("headers") or []
            self.streaming = any(
                key.lower() == b"content-type" and value.startswith(_EVENT_STREAM) for key, value in headers
            )
        elif message["type"] == "http.response.body" and not message.get("more_body", False):
            self.completed = True


class GracefulShutdownMiddleware:
    """Чистое ASGI-звено снаружи остальных: видит отмену запроса и успевает ответить сам."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        shutdown: ShutdownSignal | None = None,
        grace_s: float = 8.0,
        retry_after_s: int = RESTART_RETRY_AFTER_S,
    ) -> None:
        self.app = app
        self._shutdown = shutdown or process_shutdown()
        self._grace_s = grace_s
        self._retry_after_s = retry_after_s
        self._calls: set[_Call] = set()
        self._watcher: asyncio.Task[None] | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        task = asyncio.current_task()
        if scope["type"] != "http" or task is None:
            await self.app(scope, receive, send)
            return
        if self._stopping():
            await restarting_response(scope, self._retry_after_s)(scope, receive, send)
            return
        call = _Call(task)
        self._calls.add(call)
        self._ensure_watcher()

        async def tracked(message: Message) -> None:
            call.observe(message)
            await send(message)

        try:
            await self.app(scope, receive, tracked)
        except asyncio.CancelledError:
            if not self._stopping():
                raise
            # Запрос отменён остановкой (сторожем ниже или uvicorn по сроку): ответ закрываем сами.
            while task.uncancel():
                pass
            await self._close(call, scope, receive, send)
        finally:
            self._calls.discard(call)

    def _stopping(self) -> bool:
        # Методом, а не свойством на месте: флаг меняется между проверками, пока запрос ждёт.
        return self._shutdown.requested

    async def _close(self, call: _Call, scope: Scope, receive: Receive, send: Send) -> None:
        with contextlib.suppress(Exception):
            if not call.started:
                await restarting_response(scope, self._retry_after_s)(scope, receive, send)
            elif not call.completed:
                # Поток событий кончается штатно: EventSource переподключится уже к новому процессу.
                await send({"type": "http.response.body", "body": b"", "more_body": False})

    def _ensure_watcher(self) -> None:
        loop = asyncio.get_running_loop()
        if self._watcher is not None and not self._watcher.done() and self._watcher.get_loop() is loop:
            return
        self._watcher = loop.create_task(self._watch())

    async def _watch(self) -> None:
        await self._shutdown.wait()
        stopped = self._stop(lambda call: call.streaming)
        if stopped:
            logger.info("graceful shutdown: event streams closed", count=stopped)
        await asyncio.sleep(self._grace_s)
        stopped = self._stop(lambda _call: True)
        if stopped:
            logger.warning("graceful shutdown: requests answered 503", count=stopped)

    def _stop(self, which: Callable[[_Call], bool]) -> int:
        stopped = 0
        for call in list(self._calls):
            if not call.completed and not call.task.done() and which(call):
                call.task.cancel()
                stopped += 1
        return stopped


def _hook_signals(shutdown: ShutdownSignal) -> dict[int, Any]:
    """Флаг остановки в момент сигнала, поверх обработчика uvicorn (он ставит свой до старта приложения).

    Возвращает прежние обработчики, чтобы вернуть их при остановке приложения.
    """
    if threading.current_thread() is not threading.main_thread():
        return {}
    previous_handlers: dict[int, Any] = {}
    for sig in _HANDLED_SIGNALS:
        previous = signal.getsignal(sig)
        if not callable(previous):
            continue

        def handler(signum: int, frame: FrameType | None, _previous: Any = previous) -> None:
            shutdown.request()
            _previous(signum, frame)

        signal.signal(sig, handler)
        previous_handlers[sig] = previous
    return previous_handlers


def install_graceful_shutdown(app: FastAPI, *, timeout_graceful_shutdown: float) -> None:
    """Звено ставится последним, то есть снаружи остальных; сигнал перехватывается при старте приложения.

    Флаг поднимает только настоящий сигнал: событие `shutdown` приложения его не трогает, иначе в тестах первое же
    закрытое приложение отвечало бы 503 всем следующим в том же процессе.
    """
    shutdown = process_shutdown()
    grace_s = max(1.0, timeout_graceful_shutdown - _GRACE_MARGIN_S)
    app.add_middleware(GracefulShutdownMiddleware, shutdown=shutdown, grace_s=grace_s)
    hooked: dict[int, Any] = {}

    @app.on_event("startup")
    async def _hook_shutdown_signals() -> None:
        hooked.update(_hook_signals(shutdown))

    @app.on_event("shutdown")
    async def _unhook_shutdown_signals() -> None:
        if threading.current_thread() is not threading.main_thread():
            return
        for sig, previous in hooked.items():
            signal.signal(sig, previous)
        hooked.clear()


__all__ = [
    "SERVER_RESTARTING_CODE",
    "GracefulShutdownMiddleware",
    "install_graceful_shutdown",
    "restarting_response",
]
