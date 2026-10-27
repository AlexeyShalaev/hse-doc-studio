"""Сквозной идентификатор запроса.

Берётся из входящего ``X-Request-ID``, если он выглядит как безопасный токен, иначе генерируется. Ложится в
контекст логов (structlog) и в заголовок ответа.
"""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
_SAFE = re.compile(r"^[A-Za-z0-9._\-]{8,64}$")

_request_id: ContextVar[str | None] = ContextVar("hse_request_id", default=None)


def current_request_id() -> str | None:
    return _request_id.get()


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        incoming = next((v.decode("latin-1") for k, v in scope["headers"] if k == b"x-request-id"), "")
        request_id = incoming if _SAFE.match(incoming) else uuid.uuid4().hex
        token = _request_id.set(request_id)
        structlog.contextvars.bind_contextvars(request_id=request_id)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
            _request_id.reset(token)
