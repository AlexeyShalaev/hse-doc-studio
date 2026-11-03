"""Вход по passkey, ключи в профиле и повторное подтверждение личности (серверный режим)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.auth_cookie import credentials_from_request, is_secure_public_url, set_session_cookie
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.observability.client_ip import client_ip
from hse_doc_studio.api.passkey_party import relying_party
from hse_doc_studio.api.rate_limit import enforce_ip
from hse_doc_studio.api.routers.v1.session import session_user
from hse_doc_studio.api.schemas.passkeys import (
    AccountPasskey,
    AccountPasskeyList,
    CreatePasskeyRequest,
    PasskeyLoginRequest,
    PasskeyOptions,
    PasskeySignupOptionsRequest,
    PasskeySignupRequest,
    ReauthRequest,
    ReauthResponse,
    RenamePasskeyRequest,
)
from hse_doc_studio.api.schemas.session import LoginResponse
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import ActorSource
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import hash_token
from hse_doc_studio.core.identity.passkeys import PASSKEY_LIMIT, Passkey, RelyingParty
from hse_doc_studio.core.rate_limit import AUTH_IP, PASSKEY_IP
from hse_doc_studio.use_cases.identity.passkey_login import FinishPasskeyLoginUC, StartPasskeyLoginUC
from hse_doc_studio.use_cases.identity.passkey_signup import FinishPasskeySignupUC, StartPasskeySignupUC
from hse_doc_studio.use_cases.identity.passkeys import (
    DeletePasskeyUC,
    FinishPasskeyRegistrationUC,
    ListPasskeysUC,
    RenamePasskeyUC,
    StartPasskeyRegistrationUC,
)
from hse_doc_studio.use_cases.identity.reauth import ReauthUC, StartReauthUC

router = APIRouter(dependencies=[Depends(require_server_mode)])

_DAY_S = 24 * 60 * 60
_NO_STORE = {"Cache-Control": "no-store"}


def _session_user_id() -> str:
    """Ключами управляет только вошедший по cookie: токен доступа не добавит ключ в чужой аккаунт."""
    actor = current_actor()
    if actor is None or not actor.id:
        raise IdentityError(IdentityErrorCode.auth_required)
    if actor.source is not ActorSource.session:
        raise IdentityError(IdentityErrorCode.forbidden)
    return actor.id


def _session_hash(request: Request) -> str | None:
    secret = credentials_from_request(request).session_secret
    return hash_token(secret) if secret else None


def account_passkey(passkey: Passkey, party: RelyingParty | None) -> AccountPasskey:
    return AccountPasskey(
        id=passkey.id,
        name=passkey.name,
        created_at=passkey.created_at,
        last_used_at=passkey.last_used_at,
        synced=passkey.backup_eligible,
        domain=passkey.rp_id,
        domain_matches=party is not None and party.id == passkey.rp_id,
    )


async def _uc[T](request: Request, kind: type[T]) -> T:
    return await request.state.dishka_container.get(kind)


@router.post("/auth/passkey/options", response_model=PasskeyOptions)
async def passkey_login_options(request: Request, response: Response) -> PasskeyOptions:
    """Вызов для входа без e-mail: браузер покажет ключи этого сайта (кнопкой или в автозаполнении поля логина)."""
    await enforce_ip(request, PASSKEY_IP)
    response.headers.update(_NO_STORE)
    return PasskeyOptions(options=await (await _uc(request, StartPasskeyLoginUC)).execute(relying_party(request)))


@router.post("/auth/passkey/login", response_model=LoginResponse)
async def passkey_login(body: PasskeyLoginRequest, request: Request, response: Response) -> LoginResponse:
    await enforce_ip(request, PASSKEY_IP)
    result = await (await _uc(request, FinishPasskeyLoginUC)).execute(
        relying_party(request),
        body.credential,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        previous_secret=credentials_from_request(request).session_secret,
    )
    set_session_cookie(
        response,
        result.secret,
        secure=is_secure_public_url(settings.auth.public_url),
        max_age_s=settings.auth.session_absolute_days * _DAY_S,
    )
    response.headers.update(_NO_STORE)
    return LoginResponse(user=session_user(result.user), csrf_token=result.session.csrf_token)


@router.post("/auth/register/passkey/options", response_model=PasskeyOptions)
async def passkey_signup_options(
    body: PasskeySignupOptionsRequest, request: Request, response: Response
) -> PasskeyOptions:
    """Регистрация по приглашению на адрес сразу с passkey: параметры ключа для будущего аккаунта."""
    await enforce_ip(request, PASSKEY_IP)
    options = await (await _uc(request, StartPasskeySignupUC)).execute(
        relying_party(request), body.invitation_token, body.name
    )
    response.headers.update(_NO_STORE)
    return PasskeyOptions(options=options)


@router.post("/auth/register/passkey", response_model=LoginResponse)
async def passkey_signup(body: PasskeySignupRequest, request: Request, response: Response) -> LoginResponse:
    """Аккаунт без пароля: ключ, погашенное приглашение и сессия одним ответом (как вход)."""
    await enforce_ip(request, AUTH_IP)
    result = await (await _uc(request, FinishPasskeySignupUC)).execute(
        relying_party(request),
        body.invitation_token,
        body.name,
        body.credential,
        passkey_name=body.passkey_name,
        locale=request.headers.get("x-interface-language"),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
    )
    set_session_cookie(
        response,
        result.secret,
        secure=is_secure_public_url(settings.auth.public_url),
        max_age_s=settings.auth.session_absolute_days * _DAY_S,
    )
    response.headers.update(_NO_STORE)
    return LoginResponse(user=session_user(result.user), csrf_token=result.session.csrf_token)


@router.get("/account/passkeys", response_model=AccountPasskeyList)
async def list_passkeys(request: Request, response: Response) -> AccountPasskeyList:
    user_id = _session_user_id()
    party = relying_party(request)
    view = await (await _uc(request, ListPasskeysUC)).execute(user_id)
    response.headers.update(_NO_STORE)
    return AccountPasskeyList(
        items=[account_passkey(p, party) for p in view.items],
        enabled=view.enabled and party is not None,
        domain=party.id if party else None,
        has_password=view.has_password,
        limit=PASSKEY_LIMIT,
    )


@router.post("/account/passkeys/options", response_model=PasskeyOptions)
async def passkey_registration_options(request: Request, response: Response) -> PasskeyOptions:
    """Нужна свежая сессия (вход или подтверждение личности не старше 10 минут), иначе 403 `reauth_required`."""
    user_id = _session_user_id()
    options = await (await _uc(request, StartPasskeyRegistrationUC)).execute(
        user_id, _session_hash(request), relying_party(request)
    )
    response.headers.update(_NO_STORE)
    return PasskeyOptions(options=options)


@router.post("/account/passkeys", response_model=AccountPasskey, status_code=status.HTTP_201_CREATED)
async def create_passkey(body: CreatePasskeyRequest, request: Request, response: Response) -> AccountPasskey:
    user_id = _session_user_id()
    party = relying_party(request)
    created = await (await _uc(request, FinishPasskeyRegistrationUC)).execute(
        user_id, party, body.credential, name=body.name
    )
    response.headers.update(_NO_STORE)
    return account_passkey(created, party)


@router.patch("/account/passkeys/{passkey_id}", response_model=AccountPasskey)
async def rename_passkey(passkey_id: str, body: RenamePasskeyRequest, request: Request) -> AccountPasskey:
    renamed = await (await _uc(request, RenamePasskeyUC)).execute(_session_user_id(), passkey_id, body.name)
    return account_passkey(renamed, relying_party(request))


@router.delete("/account/passkeys/{passkey_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_passkey(passkey_id: str, request: Request) -> Response:
    """Нужна свежая сессия; последний способ войти не удаляется (409 `last_login_method`)."""
    user_id = _session_user_id()
    await (await _uc(request, DeletePasskeyUC)).execute(user_id, _session_hash(request), passkey_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=_NO_STORE)


@router.post("/account/reauth/options", response_model=PasskeyOptions)
async def reauth_options(request: Request, response: Response) -> PasskeyOptions:
    user_id = _session_user_id()
    options = await (await _uc(request, StartReauthUC)).execute(user_id, relying_party(request))
    response.headers.update(_NO_STORE)
    return PasskeyOptions(options=options)


@router.post("/account/reauth", response_model=ReauthResponse)
async def reauth(body: ReauthRequest, request: Request, response: Response) -> ReauthResponse:
    """Подтвердить личность паролем или своим passkey: открывает окно для добавления и удаления ключей."""
    await enforce_ip(request, AUTH_IP)
    user_id = _session_user_id()
    until = await (await _uc(request, ReauthUC)).execute(
        user_id,
        _session_hash(request),
        relying_party(request),
        password=body.password,
        credential=body.credential,
        ip=client_ip(request),
    )
    response.headers.update(_NO_STORE)
    return ReauthResponse(reauth_until=until)
