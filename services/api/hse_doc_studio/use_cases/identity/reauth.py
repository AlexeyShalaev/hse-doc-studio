"""Повторное подтверждение личности в открытой сессии: паролем или одним из своих passkey.

Открывает короткое окно (`REAUTH_WINDOW`), в котором можно добавлять и удалять ключи. Человек без пароля и без
passkey (только единый вход) подтверждает личность новым входом через провайдера: у новой сессии окно открыто сразу.
"""

from __future__ import annotations

import math
import secrets
from datetime import datetime

from hse_doc_studio.core.identity.entities import AuthTokenKind
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.passkeys import (
    REAUTH_WINDOW,
    CredentialJson,
    IPasskeyRepository,
    IWebAuthn,
    PasskeyVerificationError,
    RelyingParty,
)
from hse_doc_studio.core.identity.protocols import (
    IAuditLog,
    ICredentialRepository,
    ILoginAttemptRepository,
    IPasswordHasher,
    ISessionRepository,
)
from hse_doc_studio.core.identity.session_policy import Clock, login_delay, utc_now
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.identity.auth_settings import AuthSettingsService
from hse_doc_studio.use_cases.identity.passkey_ceremony import PasskeyChallenges, PasskeyPolicy
from hse_doc_studio.use_cases.identity.passkey_login import AssertionChecker
from hse_doc_studio.use_cases.identity.passkeys import descriptors


def reauth_attempt_key(user_id: str) -> str:
    return f"reauth:{user_id}"


class StartReauthUC:
    """Параметры `navigator.credentials.get()` только со своими ключами: чужой ключ браузер не предложит."""

    def __init__(
        self, passkeys: IPasskeyRepository, challenges: PasskeyChallenges, policy: PasskeyPolicy, webauthn: IWebAuthn
    ) -> None:
        self._passkeys = passkeys
        self._challenges = challenges
        self._policy = policy
        self._webauthn = webauthn

    async def execute(self, user_id: str, party: RelyingParty | None) -> dict[str, object]:
        party = await self._policy.require(party)
        own = [p for p in await self._passkeys.list_for_user(user_id) if p.rp_id == party.id]
        if not own:
            raise IdentityError(IdentityErrorCode.not_found)
        challenge = await self._challenges.issue(AuthTokenKind.passkey_reauth, user_id)
        return self._webauthn.authentication_options(party, challenge=challenge, allow=descriptors(own))


class ReauthUC:
    def __init__(
        self,
        sessions: ISessionRepository,
        credentials: ICredentialRepository,
        hasher: IPasswordHasher,
        attempts: ILoginAttemptRepository,
        passkeys: IPasskeyRepository,
        checker: AssertionChecker,
        policy: PasskeyPolicy,
        settings: AuthSettingsService,
        audit: IAuditLog,
        uow: IUnitOfWork,
        clock: Clock = utc_now,
    ) -> None:
        self._sessions = sessions
        self._credentials = credentials
        self._hasher = hasher
        self._attempts = attempts
        self._passkeys = passkeys
        self._checker = checker
        self._policy = policy
        self._settings = settings
        self._audit = audit
        self._uow = uow
        self._clock = clock
        self._dummy_hash = hasher.hash(secrets.token_urlsafe(16))

    async def execute(
        self,
        user_id: str,
        session_id_hash: str | None,
        party: RelyingParty | None,
        *,
        password: str | None = None,
        credential: CredentialJson | None = None,
        ip: str | None = None,
    ) -> datetime:
        """Ровно один способ: пароль или ответ passkey. Возвращает, до какого момента окно открыто."""
        if (password is None) == (credential is None):
            raise IdentityError(IdentityErrorCode.input_invalid)
        session = await self._sessions.get(session_id_hash) if session_id_hash else None
        if session is None or session.user_id != user_id:
            raise IdentityError(IdentityErrorCode.forbidden)
        if password is not None:
            method = "password"
            await self._check_password(user_id, password, ip)
        else:
            method = "passkey"
            await self._check_passkey(user_id, party, credential or {}, ip)
        now = self._clock()
        async with self._uow.begin():
            await self._sessions.mark_reauthenticated(session.id_hash, now)
            await self._audit.record("auth.reauth", actor_id=user_id, details={"ip": ip, "method": method})
        return now + REAUTH_WINDOW

    async def _check_password(self, user_id: str, password: str, ip: str | None) -> None:
        now = self._clock()
        key = reauth_attempt_key(user_id)
        attempt = await self._attempts.get(key)
        if attempt and attempt.next_allowed_at and attempt.next_allowed_at > now:
            wait = attempt.next_allowed_at - now
            raise IdentityError(IdentityErrorCode.rate_limited, retry_after_s=math.ceil(wait.total_seconds()))
        enabled = (await self._settings.effective()).password_enabled
        stored = await self._credentials.get_hash(user_id) if enabled else None
        if not self._hasher.verify(password, stored or self._dummy_hash) or stored is None:
            await self._attempts.record_failure(key, now, login_delay)
            await self._audit.record("auth.reauth_failed", actor_id=user_id, details={"ip": ip, "method": "password"})
            raise IdentityError(IdentityErrorCode.invalid_credentials)
        await self._attempts.reset(key)

    async def _check_passkey(
        self, user_id: str, party: RelyingParty | None, credential: CredentialJson, ip: str | None
    ) -> None:
        party = await self._policy.require(party)
        try:
            passkey, verified = await self._checker.check(
                party, credential, AuthTokenKind.passkey_reauth, user_id=user_id
            )
        except PasskeyVerificationError as failure:
            await self._audit.record(
                "auth.reauth_failed",
                actor_id=user_id,
                details={"ip": ip, "method": "passkey", "reason": failure.reason.value},
            )
            raise IdentityError(IdentityErrorCode.passkey_invalid) from failure
        await self._passkeys.record_use(
            passkey.id, sign_count=verified.new_sign_count, backed_up=verified.backed_up, now=self._clock()
        )
