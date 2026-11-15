"""HTTP-вид ошибок каталогов паков: тело `{detail, code, ...ctx}`, статус по коду (`core/pack_catalog/errors.py`)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from hse_doc_studio.core.pack_catalog.errors import CatalogError


async def _handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, CatalogError)  # noqa: S101 — обработчик зарегистрирован только на этот тип
    body = {"detail": exc.detail, "code": exc.code.value, **jsonable_encoder(exc.ctx)}
    return JSONResponse(status_code=exc.status, content=body)


def install_pack_catalog_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(CatalogError, _handler)
