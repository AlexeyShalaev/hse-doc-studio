"""Сессии аккаунта: список, отзыв одной и всех остальных (серверный режим)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, RedirectResponse

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.auth_cookie import (
    clear_session_cookie,
    credentials_from_request,
    is_secure_public_url,
    set_oidc_state_cookie,
)
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.rate_limit import enforce_email
from hse_doc_studio.api.routers.v1.oidc import oidc_failure, oidc_redirect_uri
from hse_doc_studio.api.schemas.session import (
    AccountIdentity,
    AccountProfile,
    AccountSession,
    ApiToken,
    ChangeEmailRequest,
    ChangeEmailResponse,
    ChangePasswordRequest,
    CreateApiTokenRequest,
    CreateApiTokenResponse,
    UpdateAccountRequest,
    VerifyEmailRequest,
)
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import ActorSource
from hse_doc_studio.core.identity.entities import ApiToken as ApiTokenEntity
from hse_doc_studio.core.identity.entities import TokenScope as TokenScopeEntity
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import hash_token
from hse_doc_studio.core.identity.oidc import OidcLoginError
from hse_doc_studio.core.vcs.errors import ProfileInvalidError
from hse_doc_studio.use_cases.admin.lifecycle import ExportMyDataUC
from hse_doc_studio.use_cases.identity.account_email import ConfirmEmailChangeUC, RequestEmailChangeUC
from hse_doc_studio.use_cases.identity.account_profile import (
    UNSET,
    AccountView,
    GetAccountUC,
    UpdateAccountInput,
    UpdateAccountUC,
)
from hse_doc_studio.use_cases.identity.api_tokens import CreateApiTokenUC, ListApiTokensUC, RevokeApiTokenUC
from hse_doc_studio.use_cases.identity.change_password import ChangePasswordUC
from hse_doc_studio.use_cases.identity.oidc_identities import ListOidcIdentitiesUC, UnlinkOidcIdentityUC
from hse_doc_studio.use_cases.identity.oidc_login import StartOidcLoginUC
from hse_doc_studio.use_cases.identity.sessions import (
    ListSessionsUC,
    RevokeOtherSessionsUC,
    RevokeSessionUC,
    SessionInfo,
)

router = APIRouter(dependencies=[Depends(require_server_mode)])

_PUBLIC_PREFIX = "ses_"
_PUBLIC_LENGTH = 24


def public_session_id(id_hash: str) -> str:
    """Наружу уходит укороченный хеш: по нему сессию не подставить в cookie, только отозвать."""
    return f"{_PUBLIC_PREFIX}{id_hash[:_PUBLIC_LENGTH]}"


def _user_id() -> str:
    actor = current_actor()
    if actor is None or not actor.id:
        raise IdentityError(IdentityErrorCode.auth_required)
    return actor.id


def _current_hash(request: Request) -> str:
    """Сессиями управляет только вошедший по cookie: Bearer-токену это не положено."""
    secret = credentials_from_request(request).session_secret
    if not secret:
        raise IdentityError(IdentityErrorCode.forbidden)
    return hash_token(secret)


def _item(info: SessionInfo) -> AccountSession:
    session = info.session
    return AccountSession(
        id=public_session_id(session.id_hash),
        created_at=session.created_at,
        last_seen_at=session.last_seen_at,
        ip=session.ip,
        user_agent=session.user_agent,
        current=info.current,
    )


def _profile(view: AccountView) -> AccountProfile:
    user = view.user
    locale = user.locale if user.locale in ("ru", "en") else None
    return AccountProfile(
        id=user.id,
        name=user.name,
        email=user.email,
        locale=locale,
        commit_name=user.commit_name,
        commit_email=user.commit_email,
        commit_use_account_email=user.commit_use_account_email,
        effective_commit_name=view.identity.name,
        effective_commit_email=view.identity.email,
        commit_email_is_noreply=view.identity.is_noreply,
    )


@router.get("/account", response_model=AccountProfile)
async def get_account(request: Request, response: Response) -> AccountProfile:
    response.headers["Cache-Control"] = "no-store"
    return _profile(await (await request.state.dishka_container.get(GetAccountUC)).execute(_user_id()))


@router.patch("/account", response_model=AccountProfile)
async def update_account(body: UpdateAccountRequest, request: Request, response: Response) -> AccountProfile:
    inp = UpdateAccountInput(
        name=UNSET if body.name is None else body.name,
        locale=UNSET if body.locale is None else body.locale,
        commit_name=UNSET if body.commit_name is None else body.commit_name,
        commit_email=UNSET if body.commit_email is None else body.commit_email,
        commit_use_account_email=UNSET if body.commit_use_account_email is None else body.commit_use_account_email,
    )
    try:
        view = await (await request.state.dishka_container.get(UpdateAccountUC)).execute(_user_id(), inp)
    except ProfileInvalidError as exc:
        # Тот же вид, что у ошибок проверки FastAPI, плюс код правила для подсветки поля.
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["body", e.field], "code": e.code, "msg": e.message} for e in exc.errors],
        ) from exc
    response.headers["Cache-Control"] = "no-store"
    return _profile(view)


@router.get("/account/sessions", response_model=list[AccountSession])
async def list_sessions(request: Request) -> list[AccountSession]:
    user_id = _user_id()
    uc = await request.state.dishka_container.get(ListSessionsUC)
    infos = await uc.execute(user_id, _current_hash(request))
    return [_item(info) for info in sorted(infos, key=lambda i: i.session.last_seen_at, reverse=True)]


@router.delete("/account/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(session_id: str, request: Request) -> Response:
    user_id = _user_id()
    current = _current_hash(request)
    container = request.state.dishka_container
    infos = await (await container.get(ListSessionsUC)).execute(user_id, current)
    target = next((i for i in infos if public_session_id(i.session.id_hash) == session_id), None)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    await (await container.get(RevokeSessionUC)).execute(user_id, target.session.id_hash)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    if target.current:
        clear_session_cookie(response, secure=is_secure_public_url(settings.auth.public_url))
    return response


@router.delete("/account/sessions", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_other_sessions(request: Request) -> Response:
    user_id = _user_id()
    await (await request.state.dishka_container.get(RevokeOtherSessionsUC)).execute(user_id, _current_hash(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/account/identities", response_model=list[AccountIdentity])
async def list_identities(request: Request, response: Response) -> list[AccountIdentity]:
    views = await (await request.state.dishka_container.get(ListOidcIdentitiesUC)).execute(_user_id())
    response.headers["Cache-Control"] = "no-store"
    return [
        AccountIdentity(
            provider=v.identity.provider,
            label=v.label,
            email=v.identity.email,
            email_verified=v.identity.email_verified,
        )
        for v in views
    ]


@router.get("/account/identities/{provider_id}/link", include_in_schema=False)
async def link_identity(provider_id: str, request: Request, next: str | None = None) -> RedirectResponse:  # noqa: A002
    """Начало привязки провайдера к аккаунту: вошедший по cookie уходит к провайдеру, возврат тем же callback."""
    user_id = _session_user_id()
    try:
        started = await (await request.state.dishka_container.get(StartOidcLoginUC)).execute(
            provider_id,
            redirect_uri=oidc_redirect_uri(request, provider_id),
            next_path=next,
            link_user_id=user_id,
        )
    except OidcLoginError as failure:
        return oidc_failure(request, failure)
    response = RedirectResponse(started.authorize_url, status_code=302)
    response.headers["Cache-Control"] = "no-store"
    set_oidc_state_cookie(response, started.sealed_state, secure=is_secure_public_url(settings.auth.public_url))
    return response


@router.delete("/account/identities/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_identity(provider_id: str, request: Request) -> Response:
    """Отвязка внешнего входа; последний способ войти убрать нельзя (409 last_login_method)."""
    await (await request.state.dishka_container.get(UnlinkOidcIdentityUC)).execute(_session_user_id(), provider_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"Cache-Control": "no-store"})


@router.post("/account/email", response_model=ChangeEmailResponse)
async def change_email(body: ChangeEmailRequest, request: Request, response: Response) -> ChangeEmailResponse:
    """Ссылка подтверждения уходит на новый адрес; пока её не открыли, действует прежний. В ответ ссылка не попадает."""
    user_id = _user_id()
    await enforce_email(request, body.email, action=f"change_email:{user_id}")
    await (await request.state.dishka_container.get(RequestEmailChangeUC)).execute(user_id, body.password, body.email)
    response.headers["Cache-Control"] = "no-store"
    return ChangeEmailResponse(status="check_email", link=None)


@router.post("/account/email/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_email_change(body: VerifyEmailRequest, request: Request) -> Response:
    """Ссылку открывает владелец нового ящика; вход не нужен, личность подтверждает сам одноразовый токен."""
    await (await request.state.dishka_container.get(ConfirmEmailChangeUC)).execute(body.token)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"Cache-Control": "no-store"})


@router.post("/account/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(body: ChangePasswordRequest, request: Request) -> Response:
    """Смена пароля вошедшим: нужен текущий пароль; остальные сессии закрываются, если не попросили иначе."""
    user_id = _user_id()
    await enforce_email(request, user_id, action="change_password")
    await (await request.state.dishka_container.get(ChangePasswordUC)).execute(
        user_id,
        _current_hash(request),
        body.current_password,
        body.new_password,
        sign_out_others=body.sign_out_other_sessions,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"Cache-Control": "no-store"})


def _session_user_id() -> str:
    """Токенами управляет только вошедший по cookie: украденный токен не должен плодить новые."""
    actor = current_actor()
    if actor is None or not actor.id:
        raise IdentityError(IdentityErrorCode.auth_required)
    if actor.source is not ActorSource.session:
        raise IdentityError(IdentityErrorCode.forbidden)
    return actor.id


def _token_item(token: ApiTokenEntity) -> ApiToken:
    return ApiToken(
        id=token.id,
        name=token.name,
        prefix=token.prefix,
        scopes=sorted(token.scopes, key=lambda scope: scope.value),
        created_at=token.created_at,
        expires_at=token.expires_at,
        last_used_at=token.last_used_at,
    )


@router.get("/account/export")
async def export_my_data(request: Request) -> JSONResponse:
    """Всё, что установка хранит о человеке, одним JSON-файлом. Только своя выгрузка и только сессией."""
    _session_user_id()
    actor = current_actor()
    assert actor is not None  # noqa: S101 — _session_user_id уже отказал бы без актора
    data = await (await request.state.dishka_container.get(ExportMyDataUC)).execute(actor)
    return JSONResponse(
        content=jsonable_encoder(data),
        headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="my-data.json"'},
    )


@router.get("/account/tokens", response_model=list[ApiToken])
async def list_tokens(request: Request, response: Response) -> list[ApiToken]:
    user_id = _session_user_id()
    tokens = await (await request.state.dishka_container.get(ListApiTokensUC)).execute(user_id)
    response.headers["Cache-Control"] = "no-store"
    return [_token_item(token) for token in tokens]


@router.post("/account/tokens", response_model=CreateApiTokenResponse, status_code=status.HTTP_201_CREATED)
async def create_token(body: CreateApiTokenRequest, request: Request, response: Response) -> CreateApiTokenResponse:
    """Открытое значение токена есть только в этом ответе."""
    user_id = _session_user_id()
    created = await (await request.state.dishka_container.get(CreateApiTokenUC)).execute(
        user_id, body.name, frozenset(TokenScopeEntity(scope) for scope in body.scopes), body.expires_in_days
    )
    response.headers["Cache-Control"] = "no-store"
    return CreateApiTokenResponse(token=created.secret, item=_token_item(created.item))


@router.delete("/account/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(token_id: str, request: Request) -> Response:
    user_id = _session_user_id()
    await (await request.state.dishka_container.get(RevokeApiTokenUC)).execute(user_id, token_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
