"""Ответ 422 на неверный запрос без введённых значений.

Стандартный обработчик FastAPI кладёт в ответ `input`: значение поля как прислал клиент. Для формы входа это
пароль, а для глубоко вложенного JSON кодирование `input` упирается в предел рекурсии и ответ превращается в 500
с телом запроса в журнале. Здесь остаются только `type`, `loc` и `msg`.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from hse_doc_studio.api.config import settings
from hse_doc_studio.api.git_errors import SECRET_BODY_PATHS
from hse_doc_studio.core.mode import StudioMode

_UNPROCESSABLE = 422


def _sanitized(exc: RequestValidationError) -> JSONResponse:
    detail = [
        {"type": str(item.get("type", "")), "loc": list(item.get("loc", ())), "msg": str(item.get("msg", ""))}
        for item in exc.errors()
    ]
    return JSONResponse(status_code=_UNPROCESSABLE, content={"detail": detail})


async def _validation_handler(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, RequestValidationError)  # noqa: S101 — обработчик зарегистрирован только на этот тип
    if settings.mode is StudioMode.server or SECRET_BODY_PATHS.match(request.url.path):
        return _sanitized(exc)
    # Локально ответ прежний (с `input`), пока кодирование его выдерживает.
    try:
        return await request_validation_exception_handler(request, exc)
    except RecursionError:
        return _sanitized(exc)


def install_validation_error_handler(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_handler)
