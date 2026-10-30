"""Язык интерфейса запроса из заголовка `X-Interface-Language`.

Чистое ASGI-промежуточное звено, а не декоратор промежуточного звена FastAPI: его обёртка прячет от ручек
сообщение `http.disconnect`, и `Request.is_disconnected()` никогда не видел ушедшего клиента. Долгий опрос
раннера по нему узнаёт, что раннер убит, и не отдаёт задачу в закрытое соединение.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

from hse_doc_studio.core.i18n import set_interface_language

INTERFACE_LANGUAGE_HEADER = b"x-interface-language"


class InterfaceLanguageMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            # Язык ложится в контекст запроса и наследуется фоновыми задачами, запущенными из него (ход агента).
            # Нет заголовка: None, дальше действует settings.interface_language.
            value = next((v.decode("latin-1") for k, v in scope["headers"] if k == INTERFACE_LANGUAGE_HEADER), None)
            set_interface_language(value)
        await self.app(scope, receive, send)
