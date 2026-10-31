"""HTTP-вид ошибок identity: тело `{detail, code}` и статус по коду.

Нужно войти: 401 (клиент уводит на страницу входа). Нет такого или не твоё: 404. Не хватает прав или не прошла проверка
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
_NOT_FOUND = 404
_UNAVAILABLE = 503
_GONE = 410
_BAD_GATEWAY = 502

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
    IdentityErrorCode.forbidden_role: _FORBIDDEN,
    IdentityErrorCode.setup_token_invalid: _FORBIDDEN,
    IdentityErrorCode.not_found: _NOT_FOUND,
    IdentityErrorCode.rate_limited: _LIMIT,
    IdentityErrorCode.setup_required: _UNAVAILABLE,
    IdentityErrorCode.setup_already_done: _STATE,
    IdentityErrorCode.email_taken: _STATE,
    IdentityErrorCode.last_owner: _STATE,
    IdentityErrorCode.last_admin: _STATE,
    IdentityErrorCode.setting_locked: _STATE,
    IdentityErrorCode.last_login_method: _STATE,
    IdentityErrorCode.password_policy: _INPUT,
    IdentityErrorCode.token_invalid: _INPUT,
    IdentityErrorCode.slug_reserved: _INPUT,
    IdentityErrorCode.slug_invalid: _INPUT,
    IdentityErrorCode.input_invalid: _INPUT,
    IdentityErrorCode.slug_taken: _STATE,
    IdentityErrorCode.org_has_projects: _STATE,
    IdentityErrorCode.name_taken: _STATE,
    IdentityErrorCode.already_member: _STATE,
    IdentityErrorCode.user_not_found: _NOT_FOUND,
    IdentityErrorCode.user_has_projects: _STATE,
    IdentityErrorCode.user_not_disabled: _STATE,
    IdentityErrorCode.personal_runners_disabled: _FORBIDDEN,
    IdentityErrorCode.personal_runner_limit: _STATE,
    IdentityErrorCode.runner_revoked: _STATE,
    IdentityErrorCode.runner_paused_by_admin: _FORBIDDEN,
    IdentityErrorCode.project_not_personal: _STATE,
    IdentityErrorCode.runner_pairing_invalid: _NOT_FOUND,
    IdentityErrorCode.runner_pairing_expired: _GONE,
    IdentityErrorCode.runner_pairing_used: _STATE,
    # Те же статусы, что отдают ai_relay_errors и локальный /remote-runner (раздел 9.9 спецификации).
    IdentityErrorCode.relay_unavailable: _UNAVAILABLE,
    IdentityErrorCode.relay_busy: _LIMIT,
    IdentityErrorCode.ai_provider_runner_invalid: _INPUT,
    IdentityErrorCode.remote_runner_url_invalid: _INPUT,
    IdentityErrorCode.remote_runner_unreachable: _BAD_GATEWAY,
    IdentityErrorCode.remote_runner_disabled: _STATE,
    IdentityErrorCode.links_disabled: _FORBIDDEN,
    IdentityErrorCode.link_limit: _STATE,
    IdentityErrorCode.link_role_too_high: _INPUT,
    IdentityErrorCode.link_password_invalid: _INPUT,
    IdentityErrorCode.link_revoked: _STATE,
    IdentityErrorCode.link_login_required: _UNAUTHORIZED,
    IdentityErrorCode.link_password_wrong: _FORBIDDEN,
    IdentityErrorCode.link_password_locked: _LIMIT,
    IdentityErrorCode.link_org_only: _FORBIDDEN,
    IdentityErrorCode.link_inactive: _NOT_FOUND,
    IdentityErrorCode.guest_name_required: _INPUT,
    IdentityErrorCode.guest_build_unavailable: _STATE,
    # invites
    IdentityErrorCode.invitation_pending: _STATE,
    IdentityErrorCode.invitation_limit: _STATE,
    IdentityErrorCode.external_invite_forbidden: _STATE,
    IdentityErrorCode.invitee_cannot_register: _STATE,
    IdentityErrorCode.invitation_role_too_high: _INPUT,
    IdentityErrorCode.persona_unknown: _INPUT,
    IdentityErrorCode.invitation_not_pending: _STATE,
    IdentityErrorCode.invitation_resend_too_soon: _LIMIT,
    IdentityErrorCode.invitation_expired: _GONE,
    IdentityErrorCode.invitation_email_mismatch: _FORBIDDEN,
    IdentityErrorCode.access_request_decided: _STATE,
    IdentityErrorCode.confirm_name_mismatch: _INPUT,
    IdentityErrorCode.transfer_expired: _GONE,
    IdentityErrorCode.transfer_outdated: _STATE,
}


def identity_error_body(exc: IdentityError) -> dict[str, object]:
    return {**exc.extra, "detail": exc.detail, "code": exc.code.value}


async def _identity_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, IdentityError)  # noqa: S101 — обработчик зарегистрирован только на этот тип
    headers = {"Retry-After": str(exc.retry_after_s)} if exc.retry_after_s else None
    status = exc.status or IDENTITY_ERROR_STATUS[exc.code]
    return JSONResponse(status_code=status, content=identity_error_body(exc), headers=headers)


def install_identity_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(IdentityError, _identity_error_handler)
