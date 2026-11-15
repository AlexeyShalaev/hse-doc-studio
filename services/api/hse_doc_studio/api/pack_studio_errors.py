"""HTTP-вид ошибок Студии шаблонов: тело `{detail, code, ...ctx}`, статус по коду (`core/pack_studio/errors.py`)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from hse_doc_studio.core.pack_studio.errors import PackStudioError


def pack_studio_error_body(exc: PackStudioError) -> dict[str, object]:
    return {"detail": exc.detail, "code": exc.code.value, **jsonable_encoder(exc.ctx)}


async def _handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, PackStudioError)  # noqa: S101 — обработчик зарегистрирован только на этот тип
    return JSONResponse(status_code=exc.status, content=pack_studio_error_body(exc))


def install_pack_studio_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(PackStudioError, _handler)
