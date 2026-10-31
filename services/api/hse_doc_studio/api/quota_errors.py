"""HTTP-вид отказов по квотам.

Предел размера проекта: 413 `project_quota_exceeded` и `{detail, code, used_bytes, limit_bytes}`.
Шлюз ИИ: 403 `ai_model_not_allowed`, 503 `ai_provider_unavailable` (с `Retry-After`).
Квота владельца: место 413 `owner_storage_exceeded`, остальные виды 429 `quota_exceeded`;
тело `{detail, code, resource, scope, used, limit, resets_at}` (`resets_at` пуст у места и участников).
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from hse_doc_studio.core.ai_gateway.errors import (
    AI_MODEL_NOT_ALLOWED,
    AI_PROVIDER_UNAVAILABLE,
    AiModelNotAllowedError,
    AiProviderUnavailableError,
)
from hse_doc_studio.core.projects.usage import PROJECT_QUOTA_EXCEEDED, ProjectQuotaExceededError
from hse_doc_studio.core.quotas.errors import OWNER_STORAGE_EXCEEDED, QUOTA_EXCEEDED, QuotaExceededError
from hse_doc_studio.core.quotas.kinds import QuotaKind

_TOO_LARGE = 413
_TOO_MANY = 429


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


async def _owner_quota_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, QuotaExceededError)  # noqa: S101 — обработчик зарегистрирован только на этот тип
    storage = exc.kind is QuotaKind.storage
    return JSONResponse(
        status_code=_TOO_LARGE if storage else _TOO_MANY,
        content={
            "detail": "Storage limit of the owner exceeded" if storage else "Quota exceeded",
            "code": OWNER_STORAGE_EXCEEDED if storage else QUOTA_EXCEEDED,
            "resource": exc.kind.value,
            "scope": exc.scope.value,
            "used": exc.used,
            "limit": exc.limit,
            "resets_at": exc.resets_at.isoformat() if exc.resets_at is not None else None,
        },
    )


async def _model_not_allowed_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AiModelNotAllowedError)  # noqa: S101
    return JSONResponse(
        status_code=403,
        content={
            "detail": f"Model {exc.model!r} is not allowed on this provider",
            "code": AI_MODEL_NOT_ALLOWED,
            "model": exc.model,
        },
    )


async def _provider_unavailable_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AiProviderUnavailableError)  # noqa: S101
    headers = {"Retry-After": str(max(1, int(exc.retry_after_s)))} if exc.retry_after_s else None
    return JSONResponse(
        status_code=503,
        content={"detail": "AI provider temporarily unavailable", "code": AI_PROVIDER_UNAVAILABLE},
        headers=headers,
    )


def install_quota_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ProjectQuotaExceededError, _quota_handler)
    app.add_exception_handler(QuotaExceededError, _owner_quota_handler)
    app.add_exception_handler(AiModelNotAllowedError, _model_not_allowed_handler)
    app.add_exception_handler(AiProviderUnavailableError, _provider_unavailable_handler)
