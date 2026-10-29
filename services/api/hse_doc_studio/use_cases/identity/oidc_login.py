"""Вход через OIDC: старт (адрес провайдера и состояние) и возврат (проверка, поиск человека, сессия)."""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from hse_doc_studio.core.identity.entities import Session, User
from hse_doc_studio.core.identity.normalize import hash_token, new_token
from hse_doc_studio.core.identity.oidc import (
    IOidcClient,
    IOidcProviderCatalog,
    IOidcStateCodec,
    OidcAuthorizeRequest,
    OidcErrorCode,
    OidcLoginError,
    OidcLoginState,
    safe_next,
)
from hse_doc_studio.core.identity.protocols import IAuditLog, ISessionRepository, IUserRepository
from hse_doc_studio.core.identity.session_policy import Clock, SessionPolicy, utc_now
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.identity.sessions import session_deadline

STATE_TTL = timedelta(minutes=10)


@dataclass(frozen=True)
class OidcStart:
    authorize_url: str
    # Значение cookie состояния входа.
    sealed_state: str


@dataclass(frozen=True)
class OidcSignIn:
    user: User
    session: Session
    # Значение cookie сессии: в БД лежит только хеш.
    secret: str
    next_path: str


def pkce_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")


class StartOidcLoginUC:
    def __init__(
        self, catalog: IOidcProviderCatalog, client: IOidcClient, codec: IOidcStateCodec, clock: Clock = utc_now
    ) -> None:
        self._catalog = catalog
        self._client = client
        self._codec = codec
        self._clock = clock

    async def execute(self, provider_id: str, *, redirect_uri: str, next_path: str | None) -> OidcStart:
        provider = await self._catalog.get(provider_id)
        if provider is None:
            raise OidcLoginError(OidcErrorCode.provider_unknown, provider_id)
        state = OidcLoginState(
            provider_id=provider.id,
            state=secrets.token_urlsafe(32),
            nonce=secrets.token_urlsafe(32),
            # 43..128 символов по RFC 7636: token_urlsafe(48) даёт 64.
            code_verifier=secrets.token_urlsafe(48),
            redirect_uri=redirect_uri,
            next_path=safe_next(next_path),
            expires_at=self._clock() + STATE_TTL,
        )
        url = await self._client.authorize_url(
            OidcAuthorizeRequest(
                provider=provider,
                redirect_uri=redirect_uri,
                state=state.state,
                nonce=state.nonce,
                code_challenge=pkce_challenge(state.code_verifier),
            )
        )
        return OidcStart(authorize_url=url, sealed_state=self._codec.seal(state))


class CompleteOidcLoginUC:
    """Возврат от провайдера. Входит только тот, чья внешняя учётная запись уже связана с аккаунтом."""

    def __init__(
        self,
        catalog: IOidcProviderCatalog,
        client: IOidcClient,
        codec: IOidcStateCodec,
        users: IUserRepository,
        sessions: ISessionRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        policy: SessionPolicy | None = None,
        clock: Clock = utc_now,
    ) -> None:
        self._catalog = catalog
        self._client = client
        self._codec = codec
        self._users = users
        self._sessions = sessions
        self._audit = audit
        self._uow = uow
        self._policy = policy or SessionPolicy()
        self._clock = clock

    async def execute(
        self,
        provider_id: str,
        *,
        sealed_state: str | None,
        state: str | None,
        code: str | None,
        error: str | None,
        ip: str | None = None,
        user_agent: str = "",
        previous_secret: str | None = None,
    ) -> OidcSignIn:
        now = self._clock()
        saved = self._check_state(provider_id, sealed_state, state, now)
        if error:
            raise OidcLoginError(OidcErrorCode.provider_denied, error[:64])
        if not code:
            raise OidcLoginError(OidcErrorCode.state_invalid, "no code")
        provider = await self._catalog.get(provider_id)
        if provider is None:
            raise OidcLoginError(OidcErrorCode.provider_unknown, provider_id)

        claims = await self._client.exchange(
            provider,
            code=code,
            code_verifier=saved.code_verifier,
            redirect_uri=saved.redirect_uri,
            nonce=saved.nonce,
        )
        user = await self._users.get_by_identity(provider.id, claims.subject)
        if user is None:
            await self._audit.record("auth.oidc_not_linked", actor_id=None, details={"provider": provider.id, "ip": ip})
            raise OidcLoginError(OidcErrorCode.not_linked)
        if not user.can_sign_in:
            await self._audit.record(
                "auth.oidc_denied",
                actor_id=user.id,
                details={"provider": provider.id, "ip": ip, "status": user.status.value},
            )
            raise OidcLoginError(OidcErrorCode.account_denied)

        secret, session, user = await self._open_session(user, provider.id, now, ip, user_agent, previous_secret)
        return OidcSignIn(user=user, session=session, secret=secret, next_path=saved.next_path)

    def _check_state(
        self, provider_id: str, sealed_state: str | None, state: str | None, now: datetime
    ) -> OidcLoginState:
        saved = self._codec.open(sealed_state) if sealed_state else None
        # Без состояния из своей cookie ответу провайдера верить нельзя, даже если он сообщает об отказе.
        if saved is None or not state or not secrets.compare_digest(saved.state.encode(), state.encode()):
            raise OidcLoginError(OidcErrorCode.state_invalid)
        if saved.provider_id != provider_id:
            raise OidcLoginError(OidcErrorCode.state_invalid, "provider mismatch")
        if now >= saved.expires_at:
            raise OidcLoginError(OidcErrorCode.state_expired)
        return saved

    async def _open_session(
        self, user: User, provider_id: str, now: datetime, ip: str | None, user_agent: str, previous_secret: str | None
    ) -> tuple[str, Session, User]:
        secret = new_token()
        session = Session(
            id_hash=hash_token(secret),
            user_id=user.id,
            csrf_token=new_token(),
            created_at=now,
            last_seen_at=now,
            expires_at=now,
            ip=ip,
            user_agent=user_agent[:512],
        )
        session = replace(session, expires_at=session_deadline(session, self._policy, now))
        async with self._uow.begin():
            fresh = await self._users.get_for_update(user.id)
            if fresh is None or not fresh.can_sign_in:
                raise OidcLoginError(OidcErrorCode.account_denied)
            user = replace(fresh, last_login_at=now)
            if previous_secret:
                await self._sessions.delete(hash_token(previous_secret))
            await self._sessions.add(session)
            await self._users.update(user)
            await self._audit.record(
                "auth.login", actor_id=user.id, details={"ip": ip, "method": f"oidc:{provider_id}"}
            )
        return secret, session, user
