"""Смена e-mail: новый адрес вступает в силу после подтверждения по ссылке из письма на него."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta

from hse_doc_studio.core.identity.entities import AuthToken, AuthTokenKind, MailKind
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import hash_token, new_token, normalize_email
from hse_doc_studio.core.identity.protocols import (
    IAuditLog,
    IAuthTokenRepository,
    ICredentialRepository,
    IPasswordHasher,
    IUserRepository,
)
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.identity.mail import LinkDelivery, auth_link

CONFIRM_EMAIL_PATH = "/confirm-email"
CHANGE_TTL = timedelta(hours=48)


@dataclass(frozen=True)
class EmailChangeResult:
    # Ссылка подтверждения, только когда письмо не ушло по почте.
    link: str | None = None


class RequestEmailChangeUC:
    def __init__(
        self,
        users: IUserRepository,
        credentials: ICredentialRepository,
        auth_tokens: IAuthTokenRepository,
        delivery: LinkDelivery,
        hasher: IPasswordHasher,
        audit: IAuditLog,
        uow: IUnitOfWork,
        *,
        public_url: str | None = None,
        clock: Clock = utc_now,
    ) -> None:
        self._users = users
        self._credentials = credentials
        self._auth_tokens = auth_tokens
        self._delivery = delivery
        self._hasher = hasher
        self._audit = audit
        self._uow = uow
        self._public_url = public_url
        self._clock = clock

    async def execute(self, user_id: str, password: str, new_email: str) -> EmailChangeResult:
        """Просит ссылку на новый адрес. Занятый адрес отвечает так же, как свободный (письмо не уходит)."""
        user = await self._users.get(user_id)
        stored = await self._credentials.get_hash(user_id)
        if user is None or stored is None or not self._hasher.verify(password, stored):
            await self._audit.record("auth.email_change_failed", actor_id=user_id)
            raise IdentityError(IdentityErrorCode.invalid_credentials)
        normalized = normalize_email(new_email)
        other = await self._users.get_by_email(normalized)
        if normalized == user.email_normalized or other is not None:
            await self._audit.record("auth.email_change_rejected", actor_id=user.id)
            return EmailChangeResult()
        now = self._clock()
        secret = new_token()
        async with self._uow.begin():
            await self._auth_tokens.add(
                AuthToken(
                    hash_token(secret), AuthTokenKind.change_email, user.id, now + CHANGE_TTL, payload=new_email.strip()
                )
            )
            await self._audit.record("auth.email_change_requested", actor_id=user.id)
        link = await self._delivery.deliver(
            MailKind.email_change,
            new_email.strip(),
            auth_link(self._public_url, CONFIRM_EMAIL_PATH, secret),
            now,
            locale=user.locale,
        )
        return EmailChangeResult(link)


class ConfirmEmailChangeUC:
    def __init__(
        self,
        users: IUserRepository,
        auth_tokens: IAuthTokenRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        clock: Clock = utc_now,
    ) -> None:
        self._users = users
        self._auth_tokens = auth_tokens
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def execute(self, token: str) -> None:
        async with self._uow.begin():
            consumed = await self._auth_tokens.consume(hash_token(token), AuthTokenKind.change_email, self._clock())
            user = await self._users.get(consumed.user_id) if consumed and consumed.user_id else None
            if consumed is None or user is None or not consumed.payload:
                raise IdentityError(IdentityErrorCode.token_invalid)
            # Адрес могли занять между запросом и подтверждением: репозиторий ответит email_taken.
            await self._users.update(
                replace(
                    user,
                    email=consumed.payload,
                    email_normalized=normalize_email(consumed.payload),
                    email_verified=True,
                )
            )
            await self._audit.record("auth.email_changed", actor_id=user.id, details={"old": user.email_normalized})
