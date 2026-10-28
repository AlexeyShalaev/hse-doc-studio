"""Вход и выход по паролю (серверный режим)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.auth_cookie import (
    clear_session_cookie,
    credentials_from_request,
    is_secure_public_url,
    set_session_cookie,
)
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.observability.client_ip import client_ip
from hse_doc_studio.api.rate_limit import enforce_ip
from hse_doc_studio.api.routers.v1.session import session_user
from hse_doc_studio.api.schemas.session import LoginRequest, LoginResponse
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.rate_limit import AUTH_IP
from hse_doc_studio.use_cases.identity.bootstrap import BootstrapUC
from hse_doc_studio.use_cases.identity.login import LoginUC
from hse_doc_studio.use_cases.identity.sessions import LogoutUC

router = APIRouter(dependencies=[Depends(require_server_mode)])

_DAY_S = 24 * 60 * 60


@router.post("/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request, response: Response) -> LoginResponse:
    await enforce_ip(request, AUTH_IP)
    container = request.state.dishka_container
    if not (await (await container.get(BootstrapUC)).auth_settings()).password_enabled:
        raise IdentityError(IdentityErrorCode.sso_login_required)
    credentials = credentials_from_request(request)
    result = await (await container.get(LoginUC)).execute(
        body.email,
        body.password,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        previous_secret=credentials.session_secret,
    )
    set_session_cookie(
        response,
        result.secret,
        secure=is_secure_public_url(settings.auth.public_url),
        max_age_s=settings.auth.session_absolute_days * _DAY_S,
    )
    response.headers["Cache-Control"] = "no-store"
    return LoginResponse(user=session_user(result.user), csrf_token=result.session.csrf_token)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request) -> Response:
    """Идемпотентен: без сессии или с погасшей тоже 204, cookie в любом случае очищается."""
    secret = credentials_from_request(request).session_secret
    if secret:
        await (await request.state.dishka_container.get(LogoutUC)).execute(secret)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response, secure=is_secure_public_url(settings.auth.public_url))
    return response
