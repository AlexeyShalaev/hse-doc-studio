"""Заголовки безопасности ответов и изоляция пользовательского содержимого.

Файлы проекта, превью и артефакты сборки написал пользователь, а отдаёт их тот же origin, что и интерфейс с
cookie сессии. Поэтому всё, что браузер мог бы исполнить (SVG, HTML, JS, неизвестные типы), отдаётся вложением с
CSP `sandbox` и `nosniff`; безопасные пассивные типы остаются `inline`. PDF не получает `sandbox`: встроенный
просмотрщик браузера в такой песочнице не открывается.
"""

from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import quote

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Шаблоны маршрутов (хвост), по которым пользователь получает свои байты.
USER_CONTENT_ROUTE_SUFFIXES = (
    "/files/{path:path}",
    "/git/conflicts/blob",
    "/compiles/{compile_id}/pdf",
    "/submissions/{submission_id}/download",
)
_CONTENT_METHODS = frozenset({"GET", "HEAD"})
# Типы, которые браузер показывает, не исполняя.
INLINE_CONTENT_TYPES = frozenset(
    {
        "text/plain",
        "application/json",
        "text/yaml",
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
    }
)
_UNSANDBOXED = frozenset({"application/pdf"})
_HSTS = "max-age=31536000; includeSubDomains"
_REFERRER_POLICY = "strict-origin-when-cross-origin"


def media_type_of(content_type: str) -> str:
    return content_type.split(";", 1)[0].strip().lower()


def frame_ancestors_directive(extra: Sequence[str]) -> str:
    return " ".join(["frame-ancestors", "'self'", *extra])


def content_security_policy(media_type: str, extra_ancestors: Sequence[str]) -> str:
    ancestors = frame_ancestors_directive(extra_ancestors)
    if media_type in _UNSANDBOXED:
        return f"default-src 'none'; {ancestors}"
    return f"sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:; {ancestors}"


def content_disposition(kind: str, filename: str | None) -> str:
    if not filename:
        return kind
    ascii_name = filename.encode("ascii", "ignore").decode().replace('"', "").replace("\\", "") or "file"
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"


def is_user_content(scope: Scope) -> bool:
    route_path = str(getattr(scope.get("route"), "path", ""))
    return scope["method"] in _CONTENT_METHODS and route_path.endswith(USER_CONTENT_ROUTE_SUFFIXES)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, frame_ancestors: Sequence[str] = (), hsts: bool = False) -> None:
        self.app = app
        self._ancestors = tuple(frame_ancestors)
        self._hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_secured(message: Message) -> None:
            if message["type"] == "http.response.start":
                self._apply(scope, MutableHeaders(scope=message))
            await send(message)

        await self.app(scope, receive, send_secured)

    def _apply(self, scope: Scope, headers: MutableHeaders) -> None:
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("Referrer-Policy", _REFERRER_POLICY)
        if self._hsts:
            headers.setdefault("Strict-Transport-Security", _HSTS)
        media_type = media_type_of(headers.get("content-type", ""))
        if is_user_content(scope):
            headers["Content-Security-Policy"] = content_security_policy(media_type, self._ancestors)
            if "content-disposition" not in headers:
                kind = "inline" if media_type in INLINE_CONTENT_TYPES else "attachment"
                name = str(scope.get("path_params", {}).get("path", "")).rsplit("/", 1)[-1]
                headers["Content-Disposition"] = content_disposition(kind, name or None)
            elif media_type not in INLINE_CONTENT_TYPES and headers["content-disposition"].lower().startswith("inline"):
                # Маршрут сам отдал `inline` для типа, который браузер мог бы исполнить.
                headers["Content-Disposition"] = "attachment" + headers["content-disposition"][len("inline") :]
        else:
            headers.setdefault("Content-Security-Policy", frame_ancestors_directive(self._ancestors))
