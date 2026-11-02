"""Безопасный режим при критической нехватке места: крупные записи отклоняются, остальное работает.

Нехватка места на томе роняет всё сразу: запись в базу, git, блобы. Поэтому, пока проба держит флаг, тела запросов
крупнее порога получают 507 с понятным кодом, а мелкие правки (сохранить набранное, освободить место) идут как обычно.
Вызовы раннера, вход и админка не режутся: раннер сдаёт результаты, админ чистит.
"""

from __future__ import annotations

import json

from starlette.types import ASGIApp, Receive, Scope, Send

from hse_doc_studio.core.i18n import localized_error, set_interface_language
from hse_doc_studio.core.lifecycle.disk import SAFE_MODE_MAX_BODY_BYTES, SafeMode

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH"})
_EXEMPT_PREFIXES = (
    "/api/admin",
    "/api/runner",
    "/api/updater",
    "/api/v1/runner",
    "/health",
    "/metrics",
    "/api/auth",
    "/api/v1/auth",
)
_INSUFFICIENT_STORAGE = 507


class StorageSafeModeMiddleware:
    def __init__(self, app: ASGIApp, *, safe_mode: SafeMode, max_body_bytes: int = SAFE_MODE_MAX_BODY_BYTES) -> None:
        self._app = app
        self._safe = safe_mode
        self._max = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self._safe.active and self._refuses(scope):
            await self._refuse(scope, send)
            return
        await self._app(scope, receive, send)

    def _refuses(self, scope: Scope) -> bool:
        if scope["type"] != "http" or scope["method"] not in _WRITE_METHODS:
            return False
        if scope["path"].startswith(_EXEMPT_PREFIXES):
            return False
        for name, value in scope["headers"]:
            if name == b"content-length":
                try:
                    return int(value) > self._max
                except ValueError:
                    return True
        # Длина не указана (потоковая загрузка): размер заранее неизвестен, в безопасном режиме её не принимаем.
        return any(name == b"transfer-encoding" for name, _ in scope["headers"])

    @staticmethod
    async def _refuse(scope: Scope, send: Send) -> None:
        lang = next((v.decode("latin-1") for k, v in scope["headers"] if k == b"x-interface-language"), None)
        set_interface_language(lang)
        body = json.dumps(
            {
                "detail": localized_error(
                    "На сервере критически мало места: крупные загрузки временно отключены. Сообщите администратору.",
                    "The server is critically low on disk space: large uploads are temporarily disabled. "
                    "Tell the administrator.",
                ),
                "code": "storage_critical",
            },
            ensure_ascii=False,
        ).encode()
        headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
        await send({"type": "http.response.start", "status": _INSUFFICIENT_STORAGE, "headers": headers})
        await send({"type": "http.response.body", "body": body})
