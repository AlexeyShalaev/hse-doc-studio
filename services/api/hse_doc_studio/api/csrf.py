"""Защита от CSRF для запросов с cookie сессии: синхронизатор-токен и проверка Origin.

Токен лежит в строке сессии и приходит клиенту в bootstrap и ответе входа; читаемой cookie нет, поэтому чужой
сайт токен не прочитает. Небезопасный запрос с cookie обязан прислать его в `X-CSRF-Token`. Освобождены запросы
без cookie (вход, регистрация: Origin всё равно проверяется), запросы с `Authorization: Bearer` (браузер
такой заголовок сам не подставит) и маршруты со своей подписью (раннер, обратный вызов ONLYOFFICE).
"""

from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable, Collection
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from hse_doc_studio.api.auth_cookie import credentials_from_request
from hse_doc_studio.api.identity_errors import IDENTITY_ERROR_STATUS, identity_error_body
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode

CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# Маршруты, которые авторизует подпись или токен, а не cookie.
CSRF_EXEMPT_PREFIXES = ("/api/runner/", "/api/v1/office-editor/callback")

type CsrfTokenLookup = Callable[[Scope, str], Awaitable[str | None]]


async def session_csrf_token(scope: Scope, secret: str) -> str | None:
    """Токен CSRF сессии по значению cookie; None, если сессии нет или она погасла."""
    from hse_doc_studio.use_cases.identity.sessions import SessionService  # noqa: PLC0415

    container = scope["app"].state.dishka_container
    resolved = await (await container.get(SessionService)).resolve(secret)
    return resolved.session.csrf_token if resolved else None


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower()


class CsrfMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        allowed_origins: Collection[str] = (),
        exempt_prefixes: tuple[str, ...] = CSRF_EXEMPT_PREFIXES,
        lookup: CsrfTokenLookup = session_csrf_token,
    ) -> None:
        self.app = app
        self._allowed = frozenset(_origin(o) for o in allowed_origins if o and o != "*")
        self._exempt = exempt_prefixes
        self._lookup = lookup

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in SAFE_METHODS or scope["path"].startswith(self._exempt):
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        credentials = credentials_from_request(request)
        if credentials.bearer_token is None and not await self._passes(request, credentials.session_secret):
            await self._reject(scope, receive, send)
            return
        await self.app(scope, receive, send)

    async def _passes(self, request: Request, session_secret: str | None) -> bool:
        if not self._origin_allowed(request):
            return False
        if not session_secret:
            return True
        expected = await self._lookup(request.scope, session_secret)
        if expected is None:
            # Недействительная сессия: запрос анонимный, отказ 401 даст проверка входа.
            return True
        given = request.headers.get(CSRF_HEADER, "")
        return hmac.compare_digest(given.encode(), expected.encode())

    def _origin_allowed(self, request: Request) -> bool:
        origin = request.headers.get("origin")
        if origin is None:
            return True
        origin = origin.strip().lower()
        if origin in self._allowed:
            return True
        host = request.headers.get("host", "").lower()
        return bool(host) and origin in (f"http://{host}", f"https://{host}")

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        set_interface_language(Request(scope).headers.get("x-interface-language"))
        error = IdentityError(IdentityErrorCode.csrf_failed)
        response = JSONResponse(status_code=IDENTITY_ERROR_STATUS[error.code], content=identity_error_body(error))
        await response(scope, receive, send)
