"""HTTP-вид ошибок identity: тело `{detail, code}` и статус по коду.

Нужно войти: 401 (клиент уводит на страницу входа). Не хватает прав или не прошла проверка
запроса: 403. Неверный ввод: 422. Занятое имя или адрес, уже завершённый шаг: 409. Новый код
обязан попасть в таблицу: тест сверяет её со всем перечислением.
"""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode

_UNAUTHORIZED = 401
_FORBIDDEN = 403
_INPUT = 422
_STATE = 409
_LIMIT = 429
_UNAVAILABLE = 503

IDENTITY_ERROR_STATUS: Mapping[IdentityErrorCode, int] = {
    IdentityErrorCode.auth_required: _UNAUTHORIZED,
    IdentityErrorCode.invalid_credentials: _UNAUTHORIZED,
    IdentityErrorCode.email_not_verified: _FORBIDDEN,
    IdentityErrorCode.pending_approval: _FORBIDDEN,
    IdentityErrorCode.account_disabled: _FORBIDDEN,
    IdentityErrorCode.registration_closed: _FORBIDDEN,
    IdentityErrorCode.domain_not_allowed: _FORBIDDEN,
    IdentityErrorCode.invitation_required: _FORBIDDEN,
    IdentityErrorCode.invitation_invalid: _FORBIDDEN,
    IdentityErrorCode.sso_login_required: _FORBIDDEN,
    IdentityErrorCode.csrf_failed: _FORBIDDEN,
    IdentityErrorCode.forbidden: _FORBIDDEN,
    IdentityErrorCode.setup_token_invalid: _FORBIDDEN,
    IdentityErrorCode.rate_limited: _LIMIT,
    IdentityErrorCode.setup_required: _UNAVAILABLE,
    IdentityErrorCode.setup_already_done: _STATE,
    IdentityErrorCode.email_taken: _STATE,
    IdentityErrorCode.last_owner: _STATE,
    IdentityErrorCode.setting_locked: _STATE,
    IdentityErrorCode.password_policy: _INPUT,
    IdentityErrorCode.token_invalid: _INPUT,
    IdentityErrorCode.slug_reserved: _INPUT,
    IdentityErrorCode.slug_invalid: _INPUT,
}


def identity_error_body(exc: IdentityError) -> dict[str, object]:
    return {"detail": exc.detail, "code": exc.code.value}


async def _identity_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, IdentityError)  # noqa: S101 — обработчик зарегистрирован только на этот тип
    headers = {"Retry-After": str(exc.retry_after_s)} if exc.retry_after_s else None
    return JSONResponse(status_code=IDENTITY_ERROR_STATUS[exc.code], content=identity_error_body(exc), headers=headers)


def install_identity_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(IdentityError, _identity_error_handler)
