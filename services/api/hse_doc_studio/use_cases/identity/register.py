"""Самостоятельная регистрация и по приглашению."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from hse_doc_studio.core.identity.entities import AuthToken, AuthTokenKind, MailKind, RegistrationInvite, User
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import hash_token, new_token, normalize_email
from hse_doc_studio.core.identity.passwords import check_password
from hse_doc_studio.core.identity.protocols import (
    IAuditLog,
    IAuthTokenRepository,
    ICredentialRepository,
    IPasswordHasher,
    IRegistrationInviteRepository,
    IUserRepository,
)
from hse_doc_studio.core.identity.registration import RegistrationOutcome, RegistrationPolicy, invite_usable
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.invitations.protocols import IEmailVerifiedHook
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.identity.auth_settings import AuthSettingsService
from hse_doc_studio.use_cases.identity.mail import LinkDelivery, auth_link

VERIFY_PATH = "/verify"
VERIFY_TTL = timedelta(hours=48)


@dataclass(frozen=True)
class RegisterResult:
    """Нейтральный ответ: для нового и уже занятого адреса он одинаков (кроме ссылки без SMTP)."""

    outcome: RegistrationOutcome
    # Ссылка подтверждения, только когда письмо не ушло по почте.
    link: str | None = None


class RegisterUC:
    def __init__(
        self,
        users: IUserRepository,
        credentials: ICredentialRepository,
        auth_tokens: IAuthTokenRepository,
        invites: IRegistrationInviteRepository,
        settings: AuthSettingsService,
        delivery: LinkDelivery,
        hasher: IPasswordHasher,
        audit: IAuditLog,
        uow: IUnitOfWork,
        *,
        public_url: str | None = None,
        clock: Clock = utc_now,
        email_hook: IEmailVerifiedHook | None = None,
    ) -> None:
        self._users = users
        # invites: подтверждённая при регистрации почта привязывает ожидающие приглашения в проекты.
        self._email_hook = email_hook
        self._credentials = credentials
        self._auth_tokens = auth_tokens
        self._invites = invites
        self._settings = settings
        self._delivery = delivery
        self._hasher = hasher
        self._audit = audit
        self._uow = uow
        self._public_url = public_url
        self._clock = clock

    async def execute(
        self, email: str, name: str, password: str, invitation_token: str | None = None, *, locale: str | None = None
    ) -> RegisterResult:
        now = self._clock()
        email_normalized = normalize_email(email)
        check_password(password, email)
        invite = await self._usable_invite(invitation_token, email_normalized) if invitation_token else None
        policy = RegistrationPolicy(await self._settings.effective(), smtp_enabled=self._delivery.smtp_enabled)
        decision = policy.evaluate(email, invite)
        # Хеш считается до проверки занятости адреса: время ответа не выдаёт, есть ли такой аккаунт.
        password_hash = self._hasher.hash(password)

        user = User(
            id=uuid.uuid4().hex,
            email=email.strip(),
            email_normalized=email_normalized,
            name=name.strip() or email_normalized.partition("@")[0],
            status=decision.status,
            created_at=now,
            email_verified=decision.email_verified,
            locale=locale if locale in ("ru", "en") else None,
        )
        secret = new_token() if decision.verification_token else None
        try:
            async with self._uow.begin():
                await self._users.add(user)
                await self._credentials.set_hash(user.id, password_hash)
                if invite is not None and await self._invites.consume(invite.token_hash, email, now) is None:
                    raise IdentityError(IdentityErrorCode.invitation_invalid)
                if secret is not None:
                    await self._auth_tokens.add(
                        AuthToken(hash_token(secret), AuthTokenKind.verify_email, user.id, now + VERIFY_TTL)
                    )
                await self._audit.record(
                    "auth.register",
                    actor_id=user.id,
                    details={"status": user.status.value, "invite": invite.id if invite else None},
                )
        except IdentityError as error:
            if error.code is not IdentityErrorCode.email_taken:
                raise
            await self._audit.record("auth.register_duplicate", actor_id=None, details={"email": email_normalized})
            return RegisterResult(decision.outcome)

        if user.email_verified and self._email_hook is not None:
            await self._email_hook.on_email_verified(user.id, user.email_normalized)
        link = None
        if secret is not None:
            link = await self._delivery.deliver(
                MailKind.verify_email,
                user.email,
                auth_link(self._public_url, VERIFY_PATH, secret),
                now,
                locale=user.locale,
            )
        return RegisterResult(decision.outcome, link)

    async def _usable_invite(self, token: str, email_normalized: str) -> RegistrationInvite:
        invite = await self._invites.get(hash_token(token))
        if invite is None or not invite_usable(invite, email_normalized, self._clock()):
            raise IdentityError(IdentityErrorCode.invitation_invalid)
        return invite
