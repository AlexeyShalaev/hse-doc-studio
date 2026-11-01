"""HTTP-вид ошибок бэкапов: тело `{detail, code, field?}`; статус по коду."""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from hse_doc_studio.core.backup.errors import BackupError, BackupErrorCode

BACKUP_ERROR_STATUS: Mapping[BackupErrorCode, int] = {
    BackupErrorCode.invalid_input: 422,
    BackupErrorCode.unsupported: 422,
    BackupErrorCode.not_found: 404,
    BackupErrorCode.conflict: 409,
    BackupErrorCode.already_running: 409,
    BackupErrorCode.no_destination: 409,
    BackupErrorCode.secrets_unavailable: 409,
    BackupErrorCode.unsafe_target: 409,
    BackupErrorCode.restore_busy: 409,
    BackupErrorCode.restore_unconfirmed: 422,
    BackupErrorCode.destination_unreachable: 502,
    BackupErrorCode.integrity: 502,
}


async def _handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, BackupError)  # noqa: S101 — обработчик зарегистрирован только на этот тип
    body: dict[str, object] = {"detail": exc.message, "code": exc.code.value}
    if exc.field:
        body["field"] = exc.field
    return JSONResponse(status_code=BACKUP_ERROR_STATUS[exc.code], content=body)


def install_backup_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(BackupError, _handler)
