"""Язык интерфейса из заголовка и сквозной `http.disconnect`: долгий опрос раннера узнаёт об убитом клиенте."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from hse_doc_studio.api.interface_language import InterfaceLanguageMiddleware
from hse_doc_studio.core.i18n import peek_interface_language
from starlette.types import Message

_API = Path(__file__).resolve().parents[3] / "hse_doc_studio" / "api"


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(InterfaceLanguageMiddleware)

    @app.post("/poll")
    async def poll(request: Request) -> dict[str, object]:
        gone = False
        for _ in range(5):
            gone = await request.is_disconnected()
            if gone:
                break
        return {"gone": gone, "lang": peek_interface_language()}

    return app


async def _call(app: FastAPI, messages: list[Message], headers: list[tuple[bytes, bytes]]) -> list[Message]:
    sent: list[Message] = []

    async def receive() -> Message:
        # Клиент ушёл: после тела запроса приходит только http.disconnect, сразу, без ожидания.
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/poll",
        "raw_path": b"/poll",
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
    }
    await app(scope, receive, send)
    return sent


async def test__middleware__sets_language_and_lets_the_endpoint_see_the_client_leave() -> None:
    sent = await _call(
        _app(),
        [{"type": "http.request", "body": b"", "more_body": False}],
        [(b"x-interface-language", b"en")],
    )

    body = next(m for m in sent if m["type"] == "http.response.body")["body"]
    assert body == b'{"gone":true,"lang":"en"}'


def test__api__has_no_base_http_middleware() -> None:
    """BaseHTTPMiddleware прячет http.disconnect от ручек: опрос раннера отдал бы задачу убитому раннеру."""
    offenders = [
        str(path.relative_to(_API))
        for path in _API.rglob("*.py")
        if '.middleware("http")' in path.read_text(encoding="utf-8")
        or "starlette.middleware.base" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
