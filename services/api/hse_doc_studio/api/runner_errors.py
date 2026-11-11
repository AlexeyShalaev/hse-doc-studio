"""Ошибки протокола раннера: тело `RunnerErrorBody` (`detail` и `code`) и статус по коду."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from hse_doc_studio.core.identity.errors import IdentityErrorCode, message_for
from hse_doc_studio.core.jobs.control import RunnerControlError
from hse_doc_studio.core.jobs.enums import RunnerErrorCode
from hse_doc_studio.core.jobs.errors import (
    ArtifactInvalidError,
    BlobForbiddenError,
    BlobMissingError,
    JobNotRunningError,
    NoRunnerAvailableError,
    QueuedJobNotFoundError,
    RunnerAuthError,
    StaleAttemptError,
)
from hse_doc_studio.core.jobs.relay import RelayOutOfOrderError, RelayRequestGoneError, RelayTooLargeError

RUNNER_ERROR_STATUS: Mapping[RunnerErrorCode, int] = {
    RunnerErrorCode.runner_unauthorized: 401,
    RunnerErrorCode.job_token_invalid: 401,
    RunnerErrorCode.runner_disabled: 403,
    RunnerErrorCode.runner_protocol_unsupported: 409,
    RunnerErrorCode.runner_limit: 409,
    RunnerErrorCode.slow_down: 429,
    RunnerErrorCode.relay_request_gone: 404,
    RunnerErrorCode.relay_out_of_order: 409,
    RunnerErrorCode.relay_too_large: 413,
    # Канал команд и диск раннера (`/control/*`, `/disk`).
    RunnerErrorCode.command_not_found: 404,
    RunnerErrorCode.command_finished: 409,
    RunnerErrorCode.feature_not_negotiated: 409,
    RunnerErrorCode.disk_report_too_large: 413,
}


async def _runner_auth_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RunnerAuthError)  # noqa: S101 — обработчик зарегистрирован только на этот тип
    return JSONResponse(
        status_code=RUNNER_ERROR_STATUS.get(exc.code, 401),
        content={"detail": exc.detail, "code": exc.code.value},
        headers={"WWW-Authenticate": "Bearer"} if exc.code is RunnerErrorCode.runner_unauthorized else None,
    )


async def _runner_control_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RunnerControlError)  # noqa: S101 — обработчик зарегистрирован только на этот тип
    return JSONResponse(
        status_code=RUNNER_ERROR_STATUS.get(exc.code, 409), content={"detail": exc.detail, "code": exc.code.value}
    )


async def _stale_attempt_handler(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc), "code": RunnerErrorCode.stale_attempt.value})


async def _no_runner_handler(_request: Request, exc: Exception) -> JSONResponse:
    # 409, как у прочих «окружение сборки не готово» (`image_missing`, `docker_unavailable`): клиент
    # показывает свой текст по коду, а не общий тост 5xx. Коды из каталога `contracts/server/error_codes.json`.
    assert isinstance(exc, NoRunnerAvailableError)  # noqa: S101 — обработчик зарегистрирован только на этот тип
    # `reason` уточняет код: личный раннер на паузе, раннер не в сети или раннера с тегом нет совсем;
    # тогда и `detail` называет именно эту причину, а не общий текст кода.
    reason = exc.reason
    detail = message_for(IdentityErrorCode(exc.code))
    if exc.fit is not None:
        detail = f"{exc.fit.describe()} {detail}"
    return JSONResponse(
        status_code=409,
        content={
            "detail": detail,
            "code": exc.code,
            "tags": sorted(exc.tags),
            "reason": reason.value if reason is not None else None,
        },
    )


async def _job_not_found_handler(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc), "code": RunnerErrorCode.job_not_found.value})


def _coded_handler(status: int, code: RunnerErrorCode) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def handler(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=status, content={"detail": str(exc), "code": code.value})

    return handler


def install_runner_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RunnerAuthError, _runner_auth_handler)
    app.add_exception_handler(RunnerControlError, _runner_control_handler)
    app.add_exception_handler(StaleAttemptError, _stale_attempt_handler)
    app.add_exception_handler(QueuedJobNotFoundError, _job_not_found_handler)
    app.add_exception_handler(JobNotRunningError, _coded_handler(409, RunnerErrorCode.job_not_running))
    app.add_exception_handler(NoRunnerAvailableError, _no_runner_handler)
    app.add_exception_handler(BlobForbiddenError, _coded_handler(403, RunnerErrorCode.blob_forbidden))
    app.add_exception_handler(BlobMissingError, _coded_handler(404, RunnerErrorCode.blob_missing))
    app.add_exception_handler(ArtifactInvalidError, _coded_handler(422, RunnerErrorCode.artifact_invalid))
    app.add_exception_handler(RelayRequestGoneError, _coded_handler(404, RunnerErrorCode.relay_request_gone))
    app.add_exception_handler(RelayOutOfOrderError, _coded_handler(409, RunnerErrorCode.relay_out_of_order))
    app.add_exception_handler(RelayTooLargeError, _coded_handler(413, RunnerErrorCode.relay_too_large))
