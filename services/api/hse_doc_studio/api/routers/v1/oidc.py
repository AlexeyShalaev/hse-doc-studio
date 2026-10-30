"""Единый вход через OIDC: переход к провайдеру и возврат от него (серверный режим)."""

from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.auth_cookie import (
    clear_oidc_state_cookie,
    credentials_from_request,
    is_secure_public_url,
    oidc_state_cookie_name,
    public_origin,
    set_oidc_state_cookie,
    set_session_cookie,
)
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.observability.client_ip import client_ip
from hse_doc_studio.api.rate_limit import enforce_ip
from hse_doc_studio.core.identity.oidc import OidcLoginError
from hse_doc_studio.core.rate_limit import AUTH_IP
from hse_doc_studio.use_cases.identity.oidc_login import CompleteOidcLoginUC, StartOidcLoginUC

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_server_mode)])

_DAY_S = 24 * 60 * 60
_ERROR_PAGE = "/auth/error"


def oidc_redirect_uri(request: Request, provider_id: str) -> str:
    """Адрес возврата: из public_url (его же надо зарегистрировать у провайдера), без него по адресу запроса."""
    origin = public_origin(settings.auth.public_url) or str(request.base_url).rstrip("/")
    return f"{origin}/api/v1/auth/oidc/{quote(provider_id, safe='')}/callback"


def oidc_failure(request: Request, failure: OidcLoginError) -> RedirectResponse:
    logger.info("oidc login failed: %s", failure)
    response = RedirectResponse(f"{_ERROR_PAGE}?code={failure.public_code}", status_code=302)
    response.headers["Cache-Control"] = "no-store"
    clear_oidc_state_cookie(response, secure=is_secure_public_url(settings.auth.public_url))
    return response


@router.get("/auth/oidc/{provider_id}/start", include_in_schema=False)
async def oidc_start(provider_id: str, request: Request, next: str | None = None) -> RedirectResponse:  # noqa: A002
    await enforce_ip(request, AUTH_IP)
    try:
        started = await (await request.state.dishka_container.get(StartOidcLoginUC)).execute(
            provider_id, redirect_uri=oidc_redirect_uri(request, provider_id), next_path=next
        )
    except OidcLoginError as failure:
        return oidc_failure(request, failure)
    response = RedirectResponse(started.authorize_url, status_code=302)
    response.headers["Cache-Control"] = "no-store"
    set_oidc_state_cookie(response, started.sealed_state, secure=is_secure_public_url(settings.auth.public_url))
    return response


@router.get("/auth/oidc/{provider_id}/callback", include_in_schema=False)
async def oidc_callback(
    provider_id: str,
    request: Request,
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    await enforce_ip(request, AUTH_IP)
    secure = is_secure_public_url(settings.auth.public_url)
    try:
        result = await (await request.state.dishka_container.get(CompleteOidcLoginUC)).execute(
            provider_id,
            sealed_state=request.cookies.get(oidc_state_cookie_name(secure=secure)),
            state=state,
            code=code,
            error=error,
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent", ""),
            previous_secret=credentials_from_request(request).session_secret,
        )
    except OidcLoginError as failure:
        return oidc_failure(request, failure)
    response = RedirectResponse(result.next_path, status_code=302)
    response.headers["Cache-Control"] = "no-store"
    clear_oidc_state_cookie(response, secure=secure)
    # Привязка из профиля идёт в уже открытой сессии: новую не создаём.
    if result.secret is not None:
        set_session_cookie(
            response, result.secret, secure=secure, max_age_s=settings.auth.session_absolute_days * _DAY_S
        )
    return response
