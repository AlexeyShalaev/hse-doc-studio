"""Вход через OIDC: старт (адрес провайдера и состояние) и возврат (проверка, поиск человека, сессия)."""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from hse_doc_studio.core.identity.entities import Session, User, UserIdentity, UserStatus
from hse_doc_studio.core.identity.errors import IdentityError
from hse_doc_studio.core.identity.normalize import hash_token, new_token, normalize_email
from hse_doc_studio.core.identity.oidc import (
    IOidcClient,
    IOidcProviderCatalog,
    IOidcStateCodec,
    OidcAuthorizeRequest,
    OidcClaims,
    OidcErrorCode,
    OidcLoginError,
    OidcLoginState,
    OidcProviderConfig,
    safe_next,
)
from hse_doc_studio.core.identity.protocols import IAuditLog, ISessionRepository, IUserRepository
from hse_doc_studio.core.identity.registration import RegistrationPolicy
from hse_doc_studio.core.identity.session_policy import Clock, SessionPolicy, utc_now
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.identity.auth_settings import AuthSettingsService
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
    # Для привязки из профиля новой сессии нет: человек уже вошёл.
    session: Session | None
    # Значение cookie сессии: в БД лежит только хеш.
    secret: str | None
    next_path: str
    # Привязка к аккаунту только что создана (автосвязь по почте или ручная из профиля).
    linked: bool = False
    # Аккаунт заведён этим входом (JIT).
    provisioned: bool = False


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

    async def execute(
        self, provider_id: str, *, redirect_uri: str, next_path: str | None, link_user_id: str | None = None
    ) -> OidcStart:
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
            link_user_id=link_user_id,
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
    """Возврат от провайдера: вход, связывание с аккаунтом, заведение аккаунта (JIT) или ручная привязка.

    Правила, от которых зависит безопасность аккаунтов:
    - внешняя учётная запись, уже связанная с аккаунтом, входит всегда (если аккаунт не отключён);
    - по почте связывается только подтверждённая провайдером (`email_verified`) и только с аккаунтом, чья почта
      подтверждена у нас; иначе человек входит по паролю и привязывает провайдера из профиля;
    - новый аккаунт заводится, только если провайдер включил `auto_provision`, почта подтверждена, а режим
      регистрации (`RegistrationPolicy`) пускает этот адрес.
    """

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
        *,
        auth_settings: AuthSettingsService | None = None,
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
        self._auth_settings = auth_settings

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
        if saved.link_user_id is not None:
            return await self._link_from_profile(saved, provider, claims, previous_secret, now, ip)

        user = await self._users.get_by_identity(provider.id, claims.subject)
        linked = provisioned = False
        if user is None:
            user, linked, provisioned = await self._link_or_provision(provider, claims, now, ip)
        if not user.can_sign_in:
            await self._audit.record(
                "auth.oidc_denied",
                actor_id=user.id,
                details={"provider": provider.id, "ip": ip, "status": user.status.value},
            )
            raise OidcLoginError(
                OidcErrorCode.pending_approval
                if user.status is UserStatus.pending_approval
                else OidcErrorCode.account_denied
            )

        secret, session, user = await self._open_session(user, provider.id, now, ip, user_agent, previous_secret)
        return OidcSignIn(
            user=user, session=session, secret=secret, next_path=saved.next_path, linked=linked, provisioned=provisioned
        )

    async def _link_or_provision(
        self, provider: OidcProviderConfig, claims: OidcClaims, now: datetime, ip: str | None
    ) -> tuple[User, bool, bool]:
        """Незнакомая внешняя учётная запись: связать с аккаунтом по почте, завести новый или отказать."""
        details: dict[str, object] = {"provider": provider.id, "ip": ip}
        if not claims.email or not claims.email_verified:
            await self._audit.record("auth.oidc_email_unverified", actor_id=None, details=details)
            raise OidcLoginError(OidcErrorCode.email_unverified)
        email_normalized = normalize_email(claims.email)
        existing = await self._users.get_by_email(email_normalized)
        if existing is not None:
            return await self._link_existing(existing, provider, claims, details), True, False
        if not provider.auto_provision or self._auth_settings is None:
            await self._audit.record("auth.oidc_not_linked", actor_id=None, details=details)
            raise OidcLoginError(OidcErrorCode.not_linked)
        return await self._provision(provider, claims, email_normalized, now, details), False, True

    async def _link_existing(
        self, user: User, provider: OidcProviderConfig, claims: OidcClaims, details: dict[str, object]
    ) -> User:
        # Аккаунт с неподтверждённой почтой мог завести кто угодно на чужой адрес и знает его пароль: связывать
        # с ним нельзя, иначе владелец адреса войдёт в аккаунт злоумышленника. Подтверждённой почта считается
        # только по письму: ссылки подтверждения и смены адреса анониму и запросившему не отдаются.
        if not user.email_verified:
            await self._audit.record("auth.oidc_link_refused", actor_id=user.id, details=details)
            raise OidcLoginError(OidcErrorCode.link_required)
        if not user.can_sign_in:
            return user
        # У аккаунта уже есть другой человек от этого провайдера: совпавшая почта не повод его подменять.
        if any(i.provider == provider.id for i in await self._users.list_identities(user.id)):
            await self._audit.record(
                "auth.oidc_link_refused", actor_id=user.id, details={**details, "why": "has_provider"}
            )
            raise OidcLoginError(OidcErrorCode.identity_taken)
        try:
            async with self._uow.begin():
                await self._users.add_identity(
                    UserIdentity(user.id, provider.id, claims.subject, claims.email, claims.email_verified)
                )
                await self._audit.record("auth.oidc_link", actor_id=user.id, details={**details, "how": "email"})
        except IdentityError as error:
            raise OidcLoginError(OidcErrorCode.identity_taken) from error
        return user

    async def _provision(
        self,
        provider: OidcProviderConfig,
        claims: OidcClaims,
        email_normalized: str,
        now: datetime,
        details: dict[str, object],
    ) -> User:
        assert claims.email is not None  # noqa: S101 — проверено выше
        assert self._auth_settings is not None  # noqa: S101 — проверено выше
        try:
            decision = RegistrationPolicy(await self._auth_settings.effective(), smtp_enabled=True).evaluate_external(
                claims.email
            )
        except IdentityError as error:
            await self._audit.record(
                "auth.oidc_provision_refused", actor_id=None, details={**details, "why": error.code.value}
            )
            raise OidcLoginError(OidcErrorCode.registration_denied, error.code.value) from error
        user = User(
            id=uuid.uuid4().hex,
            email=claims.email.strip(),
            email_normalized=email_normalized,
            name=(claims.name or "").strip() or email_normalized.partition("@")[0],
            status=decision.status,
            created_at=now,
            email_verified=decision.email_verified,
        )
        try:
            async with self._uow.begin():
                await self._users.add(user)
                await self._users.add_identity(
                    UserIdentity(user.id, provider.id, claims.subject, claims.email, claims.email_verified)
                )
                await self._audit.record(
                    "auth.oidc_provision", actor_id=user.id, details={**details, "status": user.status.value}
                )
        except IdentityError as error:
            # Параллельный вход тем же адресом успел раньше: новый аккаунт не заводим и не связываем вслепую.
            raise OidcLoginError(OidcErrorCode.link_required) from error
        return user

    async def _link_from_profile(
        self,
        saved: OidcLoginState,
        provider: OidcProviderConfig,
        claims: OidcClaims,
        session_secret: str | None,
        now: datetime,
        ip: str | None,
    ) -> OidcSignIn:
        """Вошедший человек привязывает провайдера: сессия в cookie должна принадлежать тому, кто начинал привязку."""
        current = await self._sessions.get(hash_token(session_secret)) if session_secret else None
        if current is None or current.expires_at <= now or current.user_id != saved.link_user_id:
            raise OidcLoginError(OidcErrorCode.state_invalid, "link session mismatch")
        user = await self._users.get(current.user_id)
        if user is None or not user.can_sign_in:
            raise OidcLoginError(OidcErrorCode.account_denied)
        owner = await self._users.get_by_identity(provider.id, claims.subject)
        if owner is not None and owner.id != user.id:
            await self._audit.record(
                "auth.oidc_link_refused",
                actor_id=user.id,
                details={"provider": provider.id, "ip": ip, "why": "identity_taken"},
            )
            raise OidcLoginError(OidcErrorCode.identity_taken)
        if owner is None and any(i.provider == provider.id for i in await self._users.list_identities(user.id)):
            raise OidcLoginError(OidcErrorCode.identity_taken)
        if owner is None:
            try:
                async with self._uow.begin():
                    await self._users.add_identity(
                        UserIdentity(user.id, provider.id, claims.subject, claims.email, claims.email_verified)
                    )
                    await self._audit.record(
                        "auth.oidc_link",
                        actor_id=user.id,
                        details={"provider": provider.id, "ip": ip, "how": "profile"},
                    )
            except IdentityError as error:
                raise OidcLoginError(OidcErrorCode.identity_taken) from error
        return OidcSignIn(user=user, session=None, secret=None, next_path=saved.next_path, linked=owner is None)

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
