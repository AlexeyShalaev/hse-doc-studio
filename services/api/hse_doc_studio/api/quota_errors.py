"""HTTP-вид отказа по пределу размера проекта: 413 и тело `{detail, code, used_bytes, limit_bytes}`."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from hse_doc_studio.core.projects.usage import PROJECT_QUOTA_EXCEEDED, ProjectQuotaExceededError

_TOO_LARGE = 413


async def _quota_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ProjectQuotaExceededError)  # noqa: S101 — обработчик зарегистрирован только на этот тип
    return JSONResponse(
        status_code=_TOO_LARGE,
        content={
            "detail": "Project storage limit exceeded",
            "code": PROJECT_QUOTA_EXCEEDED,
            "used_bytes": exc.used_bytes,
            "limit_bytes": exc.limit_bytes,
        },
    )


def install_quota_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ProjectQuotaExceededError, _quota_handler)
