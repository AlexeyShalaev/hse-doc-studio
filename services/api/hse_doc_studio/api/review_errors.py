"""HTTP-вид отказов ревью: 404, 422 на плохой ввод и 409 на несовместимое состояние, тело `{detail, code}`."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.review.entities import ReviewConflictError, ReviewInputError


async def _input_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ReviewInputError)  # noqa: S101 — обработчик зарегистрирован только на этот тип
    return JSONResponse(status_code=422, content={"detail": str(exc), "code": exc.code})


async def _conflict_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ReviewConflictError)  # noqa: S101 — обработчик зарегистрирован только на этот тип
    return JSONResponse(status_code=409, content={"detail": str(exc), "code": exc.code})


async def _not_found_handler(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc), "code": "not_found"})


def install_review_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ReviewInputError, _input_handler)
    app.add_exception_handler(ReviewConflictError, _conflict_handler)
    app.add_exception_handler(NotFoundError, _not_found_handler)
