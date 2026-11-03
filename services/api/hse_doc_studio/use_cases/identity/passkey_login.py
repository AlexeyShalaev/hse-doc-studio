"""Вход без пароля по passkey: обнаруживаемый ключ, человек выбирает его в браузере сам, e-mail не нужен."""

from __future__ import annotations

from dataclasses import replace

from hse_doc_studio.core.identity.entities import AuthTokenKind, Session, User
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import hash_token, new_token
from hse_doc_studio.core.identity.passkeys import (
    CredentialJson,
    IPasskeyRepository,
    IWebAuthn,
    Passkey,
    PasskeyFailure,
    PasskeyVerificationError,
    RelyingParty,
    VerifiedAssertion,
    user_handle_of,
)
from hse_doc_studio.core.identity.protocols import IAuditLog, ISessionRepository, IUserRepository
from hse_doc_studio.core.identity.session_policy import Clock, SessionPolicy, utc_now
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.identity.login import STATUS_ERRORS, LoginResult
from hse_doc_studio.use_cases.identity.passkey_ceremony import PasskeyChallenges, PasskeyPolicy
from hse_doc_studio.use_cases.identity.sessions import session_deadline


class StartPasskeyLoginUC:
    """Параметры для `navigator.credentials.get()` без списка ключей: браузер предложит ключи этого сайта сам."""

    def __init__(self, challenges: PasskeyChallenges, policy: PasskeyPolicy, webauthn: IWebAuthn) -> None:
        self._challenges = challenges
        self._policy = policy
        self._webauthn = webauthn

    async def execute(self, party: RelyingParty | None) -> dict[str, object]:
        party = await self._policy.require(party)
        challenge = await self._challenges.issue(AuthTokenKind.passkey_login, None)
        return self._webauthn.authentication_options(party, challenge=challenge, allow=[])


class AssertionChecker:
    """Общая часть входа и повторного подтверждения: вызов, ключ, его владелец и подпись."""

    def __init__(self, passkeys: IPasskeyRepository, challenges: PasskeyChallenges, webauthn: IWebAuthn) -> None:
        self._passkeys = passkeys
        self._challenges = challenges
        self._webauthn = webauthn

    async def check(
        self, party: RelyingParty, credential: CredentialJson, kind: AuthTokenKind, *, user_id: str | None = None
    ) -> tuple[Passkey, VerifiedAssertion]:
        """`user_id`: вызов и ключ обязаны принадлежать этому человеку (повторное подтверждение)."""
        header = self._webauthn.assertion_header(credential)
        token = await self._challenges.consume(kind, header.challenge)
        if token is None or token.user_id != user_id:
            raise PasskeyVerificationError(PasskeyFailure.challenge)
        passkey = await self._passkeys.get_by_credential_id(header.credential_id)
        if passkey is None or (user_id is not None and passkey.user_id != user_id):
            raise PasskeyVerificationError(PasskeyFailure.unknown_credential)
        if header.user_handle is not None and header.user_handle != user_handle_of(passkey.user_id):
            raise PasskeyVerificationError(PasskeyFailure.user_handle)
        verified = self._webauthn.verify_authentication(party, credential, challenge=header.challenge, passkey=passkey)
        return passkey, verified


class FinishPasskeyLoginUC:
    """Проверенный ответ открывает сессию так же, как вход по паролю: старая сессия закрывается, id ротируется.

    Счётчик подписей проверяется: ответ со счётчиком не больше сохранённого (у ключа, который его ведёт) отклоняется
    как возможная копия ключа. Синхронизируемые passkey держат счётчик нулём, для них проверка не срабатывает.
    """

    def __init__(
        self,
        users: IUserRepository,
        passkeys: IPasskeyRepository,
        sessions: ISessionRepository,
        checker: AssertionChecker,
        policy: PasskeyPolicy,
        audit: IAuditLog,
        uow: IUnitOfWork,
        session_policy: SessionPolicy | None = None,
        clock: Clock = utc_now,
    ) -> None:
        self._users = users
        self._passkeys = passkeys
        self._sessions = sessions
        self._checker = checker
        self._policy = policy
        self._audit = audit
        self._uow = uow
        self._session_policy = session_policy or SessionPolicy()
        self._clock = clock

    async def execute(
        self,
        party: RelyingParty | None,
        credential: CredentialJson,
        *,
        ip: str | None = None,
        user_agent: str = "",
        previous_secret: str | None = None,
    ) -> LoginResult:
        party = await self._policy.require(party)
        try:
            passkey, verified = await self._checker.check(party, credential, AuthTokenKind.passkey_login)
        except PasskeyVerificationError as failure:
            await self._audit.record(
                "auth.passkey_login_failed", actor_id=None, details={"ip": ip, "reason": failure.reason.value}
            )
            raise IdentityError(IdentityErrorCode.passkey_invalid) from failure
        user = await self._users.get(passkey.user_id)
        if user is None:
            raise IdentityError(IdentityErrorCode.passkey_invalid)
        denied = STATUS_ERRORS.get(user.status)
        if denied is not None:
            await self._audit.record(
                "auth.login_denied",
                actor_id=user.id,
                details={"ip": ip, "status": user.status.value, "method": "passkey"},
            )
            raise IdentityError(denied)
        return await self._open_session(user, passkey, verified, ip, user_agent, previous_secret)

    async def _open_session(
        self,
        user: User,
        passkey: Passkey,
        verified: VerifiedAssertion,
        ip: str | None,
        user_agent: str,
        previous_secret: str | None,
    ) -> LoginResult:
        now = self._clock()
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
        session = replace(session, expires_at=session_deadline(session, self._session_policy, now))
        async with self._uow.begin():
            fresh = await self._users.get_for_update(user.id)
            if fresh is None:
                raise IdentityError(IdentityErrorCode.passkey_invalid)
            denied = STATUS_ERRORS.get(fresh.status)
            if denied is not None:
                raise IdentityError(denied)
            user = replace(fresh, last_login_at=now)
            await self._passkeys.record_use(
                passkey.id, sign_count=verified.new_sign_count, backed_up=verified.backed_up, now=now
            )
            if previous_secret:
                await self._sessions.delete(hash_token(previous_secret))
            await self._sessions.add(session)
            await self._users.update(user)
            await self._audit.record(
                "auth.login", actor_id=user.id, details={"ip": ip, "method": "passkey", "device": passkey.name}
            )
        return LoginResult(user=user, session=session, secret=secret)
