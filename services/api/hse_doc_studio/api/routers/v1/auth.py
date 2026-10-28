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
from hse_doc_studio.api.rate_limit import email_send_allowed, enforce_email, enforce_ip
from hse_doc_studio.api.routers.v1.session import session_user
from hse_doc_studio.api.schemas.session import (
    ForgotRequest,
    ForgotResponse,
    InvitationInfo,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationRequest,
    ResetRequest,
    VerifyEmailRequest,
)
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.registration import RegistrationOutcome
from hse_doc_studio.core.rate_limit import AUTH_IP
from hse_doc_studio.use_cases.identity.bootstrap import BootstrapUC
from hse_doc_studio.use_cases.identity.invites import InvitationInfoUC
from hse_doc_studio.use_cases.identity.login import LoginUC
from hse_doc_studio.use_cases.identity.recovery import (
    ForgotPasswordUC,
    ResendVerificationUC,
    ResetPasswordUC,
    VerifyEmailUC,
)
from hse_doc_studio.use_cases.identity.register import RegisterUC
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


@router.post("/auth/verify", status_code=status.HTTP_204_NO_CONTENT)
async def verify_email(body: VerifyEmailRequest, request: Request) -> Response:
    await enforce_ip(request, AUTH_IP)
    await (await request.state.dishka_container.get(VerifyEmailUC)).execute(body.token)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"Cache-Control": "no-store"})


@router.post("/auth/verify/resend", response_model=ForgotResponse)
async def resend_verification(body: ResendVerificationRequest, request: Request, response: Response) -> ForgotResponse:
    """Всегда один и тот же ответ: по нему не узнать, есть ли такой аккаунт. Ссылка уходит только на почту."""
    await enforce_ip(request, AUTH_IP)
    # Сверх лимита письмо молча не шлём, а ответ тот же: по нему адрес не различить и сброс владельцу не закрыть.
    if await email_send_allowed(request, body.email, "verify_resend"):
        await (await request.state.dishka_container.get(ResendVerificationUC)).execute(body.email)
    response.headers["Cache-Control"] = "no-store"
    return ForgotResponse(status="check_email", link=None)


@router.post("/auth/forgot", response_model=ForgotResponse)
async def forgot_password(body: ForgotRequest, request: Request, response: Response) -> ForgotResponse:
    """Ответ нейтральный. Ссылку сброса не показываем и без SMTP: её выдаёт администратор."""
    await enforce_ip(request, AUTH_IP)
    # Сверх лимита письмо молча не шлём, а ответ тот же: по нему адрес не различить и сброс владельцу не закрыть.
    if await email_send_allowed(request, body.email, "forgot"):
        await (await request.state.dishka_container.get(ForgotPasswordUC)).execute(body.email)
    response.headers["Cache-Control"] = "no-store"
    return ForgotResponse(status="check_email", link=None)


@router.post("/auth/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(body: ResetRequest, request: Request) -> Response:
    await enforce_ip(request, AUTH_IP)
    await (await request.state.dishka_container.get(ResetPasswordUC)).execute(body.token, body.password)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"Cache-Control": "no-store"})


@router.post("/auth/register", response_model=RegisterResponse)
async def register(body: RegisterRequest, request: Request, response: Response) -> RegisterResponse:
    """Ответ нейтральный: для нового и уже занятого адреса одинаковый. Ссылка в ответе только без SMTP."""
    await enforce_ip(request, AUTH_IP)
    await enforce_email(request, body.email, action="register")
    language = request.headers.get("x-interface-language")
    result = await (await request.state.dishka_container.get(RegisterUC)).execute(
        body.email, body.name, body.password, body.invitation_token, locale=language
    )
    response.headers["Cache-Control"] = "no-store"
    # Контракт знает два исхода. Приглашённый на свой адрес уже активен и подтверждён, но ответ ему тот же:
    # форма ведёт на вход, а по другому ответу нельзя было бы отличить занятый адрес.
    outcome = "pending_approval" if result.outcome is RegistrationOutcome.pending_approval else "check_email"
    return RegisterResponse(status=outcome, link=result.link)


@router.get("/auth/invitations/{token}", response_model=InvitationInfo)
async def invitation_info(token: str, request: Request, response: Response) -> InvitationInfo:
    """Карточка приглашения для формы регистрации; для негодного, просроченного и отозванного токена ответ один."""
    await enforce_ip(request, AUTH_IP)
    info = await (await request.state.dishka_container.get(InvitationInfoUC)).execute(token)
    response.headers["Cache-Control"] = "no-store"
    # Организаций в M1 нет: название не показываем, даже если приглашение на неё ссылается.
    return InvitationInfo(email=info.email or "", invited_by=info.invited_by, org_name=None)
