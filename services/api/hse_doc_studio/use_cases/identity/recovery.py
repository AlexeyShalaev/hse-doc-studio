"""Подтверждение почты и сброс пароля по одноразовой ссылке."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.entities import AuthToken, AuthTokenKind, MailKind, User, UserStatus
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import hash_token, new_token, normalize_email
from hse_doc_studio.core.identity.passwords import check_password
from hse_doc_studio.core.identity.protocols import (
    IAuditLog,
    IAuthTokenRepository,
    ICredentialRepository,
    IPasswordHasher,
    ISessionRepository,
    IUserRepository,
)
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.invitations.protocols import IEmailVerifiedHook
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.identity.mail import LinkDelivery, auth_link

VERIFY_PATH = "/verify"
RESET_PATH = "/reset"
VERIFY_TTL = timedelta(hours=48)
RESET_TTL = timedelta(hours=1)
# Ссылку, выданную администратором, человек может открыть не сразу.
ADMIN_RESET_TTL = timedelta(hours=24)

# Кому имеет смысл повторно слать подтверждение: подтверждённым и отключённым не нужно.
_VERIFIABLE = frozenset({UserStatus.active, UserStatus.pending_verification, UserStatus.pending_approval})


class VerifyEmailUC:
    def __init__(
        self,
        users: IUserRepository,
        auth_tokens: IAuthTokenRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        clock: Clock = utc_now,
        email_hook: IEmailVerifiedHook | None = None,
    ) -> None:
        # invites: подтверждённая почта привязывает ожидающие приглашения в проекты.
        self._email_hook = email_hook
        self._users = users
        self._auth_tokens = auth_tokens
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def execute(self, token: str) -> None:
        """Погашенная, просроченная и неизвестная ссылки дают один и тот же отказ."""
        async with self._uow.begin():
            consumed = await self._auth_tokens.consume(hash_token(token), AuthTokenKind.verify_email, self._clock())
            user = await self._users.get_for_update(consumed.user_id) if consumed and consumed.user_id else None
            if user is None:
                raise IdentityError(IdentityErrorCode.token_invalid)
            status = UserStatus.active if user.status is UserStatus.pending_verification else user.status
            if not user.email_verified or status is not user.status:
                await self._users.update(replace(user, email_verified=True, status=status))
            await self._auth_tokens.invalidate_for_user(user.id, AuthTokenKind.verify_email, self._clock())
            await self._audit.record("auth.email_verified", actor_id=user.id)
        if self._email_hook is not None:
            await self._email_hook.on_email_verified(user.id, user.email_normalized)


class _TokenIssuer:
    """Выдаёт токен и отправляет письмо: общий кусок повторной отправки подтверждения и сброса."""

    def __init__(
        self,
        auth_tokens: IAuthTokenRepository,
        delivery: LinkDelivery,
        uow: IUnitOfWork,
        public_url: str | None,
        clock: Clock,
    ) -> None:
        self._auth_tokens = auth_tokens
        self._delivery = delivery
        self._uow = uow
        self._public_url = public_url
        self._clock = clock

    async def issue(self, user: User, kind: AuthTokenKind, mail: MailKind, path: str, ttl: timedelta) -> str | None:
        """Ссылка для показа, если письмо не ушло по почте; ошибки доставки не всплывают."""
        now: datetime = self._clock()
        secret = new_token()
        async with self._uow.begin():
            # Действует только последняя ссылка: ушедшая раньше (и, возможно, утёкшая) больше не сработает.
            # Цена: чужой POST /auth/forgot на адрес жертвы гасит её свежую ссылку, и ей нужно взять письмо
            # поновее. Принято: ответ нейтральный, запросы ограничены по (ip, email).
            await self._auth_tokens.invalidate_for_user(user.id, kind, now)
            await self._auth_tokens.add(AuthToken(hash_token(secret), kind, user.id, now + ttl))
        return await self._delivery.deliver(
            mail, user.email, auth_link(self._public_url, path, secret), now, locale=user.locale
        )


class ResendVerificationUC:
    """Ответ не зависит от того, есть ли такой аккаунт; ссылка уходит только на сам адрес."""

    def __init__(
        self,
        users: IUserRepository,
        auth_tokens: IAuthTokenRepository,
        delivery: LinkDelivery,
        audit: IAuditLog,
        uow: IUnitOfWork,
        *,
        public_url: str | None = None,
        clock: Clock = utc_now,
    ) -> None:
        self._users = users
        self._audit = audit
        self._issuer = _TokenIssuer(auth_tokens, delivery, uow, public_url, clock)

    async def execute(self, email: str) -> None:
        user = await self._users.get_by_email(normalize_email(email))
        if user is None or user.email_verified or user.status not in _VERIFIABLE:
            return
        await self._issuer.issue(user, AuthTokenKind.verify_email, MailKind.verify_email, VERIFY_PATH, VERIFY_TTL)
        await self._audit.record("auth.verification_resent", actor_id=user.id)


class ForgotPasswordUC:
    """Ссылка сброса уходит только на почту аккаунта.

    Без SMTP письмо остаётся в outbox, а не показывается на экране: иначе любой, кто знает адрес,
    сбросил бы чужой пароль. Сброс в такой установке выдаёт администратор.
    """

    def __init__(
        self,
        users: IUserRepository,
        auth_tokens: IAuthTokenRepository,
        delivery: LinkDelivery,
        audit: IAuditLog,
        uow: IUnitOfWork,
        *,
        public_url: str | None = None,
        clock: Clock = utc_now,
    ) -> None:
        self._users = users
        self._audit = audit
        self._issuer = _TokenIssuer(auth_tokens, delivery, uow, public_url, clock)

    async def execute(self, email: str) -> None:
        user = await self._users.get_by_email(normalize_email(email))
        if user is None or not user.can_sign_in:
            return
        await self._issuer.issue(user, AuthTokenKind.reset_password, MailKind.reset_password, RESET_PATH, RESET_TTL)
        await self._audit.record("auth.password_reset_requested", actor_id=user.id)


class ResetPasswordUC:
    def __init__(
        self,
        users: IUserRepository,
        credentials: ICredentialRepository,
        auth_tokens: IAuthTokenRepository,
        sessions: ISessionRepository,
        hasher: IPasswordHasher,
        audit: IAuditLog,
        uow: IUnitOfWork,
        clock: Clock = utc_now,
    ) -> None:
        self._users = users
        self._credentials = credentials
        self._auth_tokens = auth_tokens
        self._sessions = sessions
        self._hasher = hasher
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def execute(self, token: str, new_password: str) -> None:
        """Задаёт пароль и закрывает все сессии: тот, кто знал старый пароль, не остаётся внутри."""
        check_password(new_password)
        new_hash = self._hasher.hash(new_password)
        async with self._uow.begin():
            consumed = await self._auth_tokens.consume(hash_token(token), AuthTokenKind.reset_password, self._clock())
            user = await self._users.get(consumed.user_id) if consumed and consumed.user_id else None
            if user is None or not user.can_sign_in:
                raise IdentityError(IdentityErrorCode.token_invalid)
            # Пароль, равный адресу, виден только теперь; отказ откатывает и погашение ссылки.
            check_password(new_password, user.email)
            await self._credentials.set_hash(user.id, new_hash)
            # Остальные неиспользованные ссылки сброса (прежние запросы, ссылка администратора) тоже гаснут.
            await self._auth_tokens.invalidate_for_user(user.id, AuthTokenKind.reset_password, self._clock())
            revoked = await self._sessions.delete_for_user(user.id)
            await self._audit.record("auth.password_reset", actor_id=user.id, details={"revoked_sessions": revoked})


@dataclass(frozen=True)
class ResetLink:
    link: str
    expires_at: datetime
    # Ушло ли пользователю письмо о том, что ссылку выдал администратор.
    user_notified: bool


class IssueResetLinkUC:
    """Сброс пароля руками администратора: путь для установок без SMTP и для утерянной почты.

    Это явный захват аккаунта (break-glass): нужно подтверждение, событие аудита и уведомление
    владельца аккаунта, если есть почта.
    """

    def __init__(
        self,
        users: IUserRepository,
        auth_tokens: IAuthTokenRepository,
        delivery: LinkDelivery,
        audit: IAuditLog,
        uow: IUnitOfWork,
        *,
        public_url: str | None = None,
        clock: Clock = utc_now,
    ) -> None:
        self._users = users
        self._auth_tokens = auth_tokens
        self._delivery = delivery
        self._audit = audit
        self._uow = uow
        self._public_url = public_url
        self._clock = clock

    async def execute(self, actor: Actor, user_id: str, *, confirmed: bool) -> ResetLink:
        if not actor.is_instance_admin or actor.id is None or not confirmed:
            raise IdentityError(IdentityErrorCode.forbidden)
        user = await self._users.get(user_id)
        if user is None:
            raise IdentityError(IdentityErrorCode.forbidden)
        now = self._clock()
        secret = new_token()
        expires_at = now + ADMIN_RESET_TTL
        async with self._uow.begin():
            await self._auth_tokens.invalidate_for_user(user.id, AuthTokenKind.reset_password, now)
            await self._auth_tokens.add(
                AuthToken(hash_token(secret), AuthTokenKind.reset_password, user.id, expires_at)
            )
            await self._audit.record(
                "admin.reset_link_issued", actor_id=actor.id, target=user.id, details={"break_glass": True}
            )
        notified = await self._delivery.notify(MailKind.reset_notice, user.email, locale=user.locale)
        return ResetLink(auth_link(self._public_url, RESET_PATH, secret), expires_at, notified)
