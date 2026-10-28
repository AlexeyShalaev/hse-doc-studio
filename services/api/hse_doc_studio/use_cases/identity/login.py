"""Вход по паролю."""

from __future__ import annotations

import math
import secrets
from dataclasses import dataclass, replace
from datetime import datetime

from hse_doc_studio.core.identity.entities import Session, User, UserStatus
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import hash_token, new_token, normalize_email
from hse_doc_studio.core.identity.protocols import (
    IAuditLog,
    ICredentialRepository,
    ILoginAttemptRepository,
    IPasswordHasher,
    ISessionRepository,
    IUserRepository,
)
from hse_doc_studio.core.identity.session_policy import Clock, SessionPolicy, login_delay, utc_now
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.identity.sessions import session_deadline

_STATUS_ERRORS = {
    UserStatus.pending_verification: IdentityErrorCode.email_not_verified,
    UserStatus.pending_approval: IdentityErrorCode.pending_approval,
    UserStatus.disabled: IdentityErrorCode.account_disabled,
}


@dataclass(frozen=True)
class LoginResult:
    user: User
    session: Session
    # Значение cookie: существует только здесь, в БД лежит его хеш.
    secret: str


def attempt_key(email_normalized: str, ip: str | None) -> str:
    return f"login:{email_normalized}|{ip or '-'}"


class LoginUC:
    def __init__(
        self,
        users: IUserRepository,
        credentials: ICredentialRepository,
        sessions: ISessionRepository,
        attempts: ILoginAttemptRepository,
        hasher: IPasswordHasher,
        audit: IAuditLog,
        uow: IUnitOfWork,
        policy: SessionPolicy | None = None,
        clock: Clock = utc_now,
    ) -> None:
        self._users = users
        self._credentials = credentials
        self._sessions = sessions
        self._attempts = attempts
        self._hasher = hasher
        self._audit = audit
        self._uow = uow
        self._policy = policy or SessionPolicy()
        self._clock = clock
        # Для неизвестного e-mail проверяем пароль против этого хеша: стоимость ответа та же, что у известного.
        self._dummy_hash = hasher.hash(secrets.token_urlsafe(16))

    async def execute(
        self,
        email: str,
        password: str,
        *,
        ip: str | None = None,
        user_agent: str = "",
        previous_secret: str | None = None,
    ) -> LoginResult:
        """Вход создаёт новую сессию; прежняя (`previous_secret`) закрывается, id сессии ротируется."""
        now = self._clock()
        email_normalized = normalize_email(email)
        key = attempt_key(email_normalized, ip)
        await self._ensure_allowed(key, now)

        user = await self._users.get_by_email(email_normalized)
        stored = await self._credentials.get_hash(user.id) if user else None
        password_ok = self._hasher.verify(password, stored or self._dummy_hash)
        if user is None or stored is None or not password_ok:
            await self._attempts.record_failure(key, now, login_delay)
            await self._audit.record(
                "auth.login_failed", actor_id=user.id if user else None, details={"ip": ip, "email": email_normalized}
            )
            raise IdentityError(IdentityErrorCode.invalid_credentials)

        denied = _STATUS_ERRORS.get(user.status)
        if denied is not None:
            await self._audit.record(
                "auth.login_denied", actor_id=user.id, details={"ip": ip, "status": user.status.value}
            )
            raise IdentityError(denied)

        new_hash = self._hasher.hash(password) if self._hasher.needs_rehash(stored) else None
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
        user = replace(user, last_login_at=now)
        async with self._uow.begin():
            if new_hash is not None:
                await self._credentials.set_hash(user.id, new_hash)
            if previous_secret:
                await self._sessions.delete(hash_token(previous_secret))
            await self._sessions.add(session)
            await self._users.update(user)
            await self._attempts.reset(key)
            await self._audit.record("auth.login", actor_id=user.id, details={"ip": ip})
        return LoginResult(user=user, session=session, secret=secret)

    async def _ensure_allowed(self, key: str, now: datetime) -> None:
        attempt = await self._attempts.get(key)
        if attempt and attempt.next_allowed_at and attempt.next_allowed_at > now:
            wait = attempt.next_allowed_at - now
            raise IdentityError(IdentityErrorCode.rate_limited, retry_after_s=math.ceil(wait.total_seconds()))
