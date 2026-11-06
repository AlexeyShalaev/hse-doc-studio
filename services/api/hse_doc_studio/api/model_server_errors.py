"""HTTP-вид ошибок серверов моделей: тело `{detail, code}`, статус по коду."""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from hse_doc_studio.core.model_servers import ModelServerError, ModelServerErrorCode

MODEL_SERVER_ERROR_STATUS: Mapping[ModelServerErrorCode, int] = {
    ModelServerErrorCode.local_install_disabled: 409,
    ModelServerErrorCode.docker_unavailable: 409,
    ModelServerErrorCode.engine_requires_gpu: 409,
    ModelServerErrorCode.too_large: 409,
    ModelServerErrorCode.busy: 409,
    ModelServerErrorCode.start_failed: 502,
    ModelServerErrorCode.invalid_input: 422,
    ModelServerErrorCode.not_found: 404,
}


async def _handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ModelServerError)  # noqa: S101 — обработчик зарегистрирован только на этот тип
    return JSONResponse(
        status_code=MODEL_SERVER_ERROR_STATUS[exc.code], content={"detail": exc.message, "code": exc.code.value}
    )


def install_model_server_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ModelServerError, _handler)
