"""Потолок размера тела для загрузки проекта: отказ до того, как Starlette сложит multipart на диск.

Обработчик `/projects/import` видит файл уже после разбора формы во временный файл, поэтому проверка внутри него
не защищает диск. Здесь предел проверяется по `Content-Length` и по фактически принятым байтам (длина может быть
не указана или соврана).
"""

from __future__ import annotations

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from hse_doc_studio.core.i18n import localized_error, set_interface_language

# Служебные поля multipart сверх самого файла.
BODY_OVERHEAD_BYTES = 1024 * 1024
_TOO_LARGE = 413


class _BodyTooLargeError(Exception):
    pass


class UploadBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, *, path_suffix: str, max_bytes: int) -> None:
        self._app = app
        self._suffix = path_suffix
        self._max = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._watched(scope):
            await self._app(scope, receive, send)
        elif self._declared(scope) > self._max:
            await self._refuse(scope, send)
        else:
            await self._guarded(scope, receive, send)

    def _watched(self, scope: Scope) -> bool:
        return scope["type"] == "http" and scope["method"] == "POST" and scope["path"].endswith(self._suffix)

    async def _guarded(self, scope: Scope, receive: Receive, send: Send) -> None:
        received = 0
        started = False

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self._max:
                    raise _BodyTooLargeError
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self._app(scope, counting_receive, tracking_send)
        except _BodyTooLargeError:
            if started:
                raise
            await self._refuse(scope, send)

    @staticmethod
    def _declared(scope: Scope) -> int:
        for name, value in scope["headers"]:
            if name == b"content-length":
                try:
                    return int(value)
                except ValueError:
                    return 0
        return 0

    async def _refuse(self, scope: Scope, send: Send) -> None:
        # Слой снаружи языкового middleware: язык берём из заголовка сами.
        lang = next((v.decode("latin-1") for k, v in scope["headers"] if k == b"x-interface-language"), None)
        set_interface_language(lang)
        mib = (self._max - BODY_OVERHEAD_BYTES) // (1024 * 1024)
        body = json.dumps(
            {
                "detail": localized_error(
                    f"Архив больше допустимого: не более {mib} МБ.", f"The archive is too large: at most {mib} MB."
                ),
                "code": "import_too_large",
            },
            ensure_ascii=False,
        ).encode()
        headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
        await send({"type": "http.response.start", "status": _TOO_LARGE, "headers": headers})
        await send({"type": "http.response.body", "body": body})
