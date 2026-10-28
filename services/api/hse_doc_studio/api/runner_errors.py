"""Ошибки протокола раннера: тело `RunnerErrorBody` (`detail` и `code`) и статус по коду."""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from hse_doc_studio.core.jobs.enums import RunnerErrorCode
from hse_doc_studio.core.jobs.errors import RunnerAuthError

RUNNER_ERROR_STATUS: Mapping[RunnerErrorCode, int] = {
    RunnerErrorCode.runner_unauthorized: 401,
    RunnerErrorCode.job_token_invalid: 401,
    RunnerErrorCode.runner_disabled: 403,
    RunnerErrorCode.runner_protocol_unsupported: 409,
}


async def _runner_auth_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RunnerAuthError)  # noqa: S101 — обработчик зарегистрирован только на этот тип
    return JSONResponse(
        status_code=RUNNER_ERROR_STATUS.get(exc.code, 401),
        content={"detail": exc.detail, "code": exc.code.value},
        headers={"WWW-Authenticate": "Bearer"} if exc.code is RunnerErrorCode.runner_unauthorized else None,
    )


def install_runner_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RunnerAuthError, _runner_auth_handler)
