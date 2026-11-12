"""HTTP-вид отказа сборки пакета сдачи: 400 `{detail, code, doc_id, ...}` (docs/design/signing-route.md, 12.8.1).

Поля рядом с кодом (`doc`, `slot`, `who`, `step`, `total`, `hint`, `format`) фронтенд подставляет в текст
`errors:code.<код>`. Роутер пакета пропускает `PackError` мимо своего общего `ValueError`, чтобы код дошёл сюда.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from hse_doc_studio.core.submission_errors import PackError


async def _pack_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, PackError)  # noqa: S101 — обработчик зарегистрирован только на этот тип
    return JSONResponse(status_code=400, content=exc.body())


def install_submission_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(PackError, _pack_handler)
