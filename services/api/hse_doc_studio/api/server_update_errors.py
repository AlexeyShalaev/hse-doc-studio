"""HTTP-вид ошибок автообновления: тело `{detail, code, field?}`."""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from hse_doc_studio.core.server_update.errors import UpdateError, UpdateErrorCode

UPDATE_ERROR_STATUS: Mapping[UpdateErrorCode, int] = {
    UpdateErrorCode.invalid_input: 422,
    UpdateErrorCode.not_found: 404,
    UpdateErrorCode.unauthorized: 401,
    UpdateErrorCode.executor_unavailable: 409,
    UpdateErrorCode.updater_offline: 409,
    UpdateErrorCode.already_running: 409,
    UpdateErrorCode.nothing_to_update: 409,
    UpdateErrorCode.unknown_version: 422,
    UpdateErrorCode.no_previous_version: 409,
    UpdateErrorCode.not_cancellable: 409,
    UpdateErrorCode.unsafe_version_jump: 409,
    UpdateErrorCode.risk_not_confirmed: 422,
    UpdateErrorCode.rollback_unsafe: 409,
}


async def _handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, UpdateError)  # noqa: S101 — обработчик зарегистрирован только на этот тип
    body: dict[str, object] = {"detail": exc.message, "code": exc.code.value}
    if exc.field:
        body["field"] = exc.field
    return JSONResponse(status_code=UPDATE_ERROR_STATUS[exc.code], content=body)


def install_update_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(UpdateError, _handler)
