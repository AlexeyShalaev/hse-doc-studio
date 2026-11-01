"""Сессии: разрешение cookie в пользователя со скользящим сроком, список, отзыв, выход."""

from __future__ import annotations

import hmac
from dataclasses import dataclass, replace
from datetime import datetime

from hse_doc_studio.core.identity.entities import Session, User
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import hash_token
from hse_doc_studio.core.identity.protocols import IAuditLog, ISessionRepository, IUserRepository
from hse_doc_studio.core.identity.session_policy import Clock, SessionPolicy, utc_now
from hse_doc_studio.core.uow import IUnitOfWork


@dataclass(frozen=True)
class ResolvedSession:
    user: User
    session: Session


@dataclass(frozen=True)
class SessionInfo:
    session: Session
    current: bool


def session_deadline(session: Session, policy: SessionPolicy, now: datetime) -> datetime:
    """Когда сессия погаснет, если её продлить в момент `now`: скользящий срок под потолком абсолютного."""
    return min(now + policy.idle, session.created_at + policy.absolute)


class SessionService:
    def __init__(
        self,
        sessions: ISessionRepository,
        users: IUserRepository,
        policy: SessionPolicy | None = None,
        clock: Clock = utc_now,
    ) -> None:
        self._sessions = sessions
        self._users = users
        self._policy = policy or SessionPolicy()
        self._clock = clock

    async def resolve(self, secret: str) -> ResolvedSession | None:
        """Сессия и её пользователь по значению cookie либо None. Истёкшая сессия удаляется."""
        if not secret:
            return None
        id_hash = hash_token(secret)
        session = await self._sessions.get(id_hash)
        if session is None or not hmac.compare_digest(session.id_hash, id_hash):
            return None
        now = self._clock()
        if now >= session.expires_at or now >= session.created_at + self._policy.absolute:
            await self._sessions.delete(id_hash)
            return None
        user = await self._users.get(session.user_id)
        if user is None or not user.can_sign_in:
            return None
        if now - session.last_seen_at >= self._policy.touch_interval:
            expires_at = session_deadline(session, self._policy, now)
            await self._sessions.touch(id_hash, now, expires_at)
            session = replace(session, last_seen_at=now, expires_at=expires_at)
        return ResolvedSession(user=user, session=session)


class LogoutUC:
    def __init__(self, sessions: ISessionRepository, audit: IAuditLog, uow: IUnitOfWork) -> None:
        self._sessions = sessions
        self._audit = audit
        self._uow = uow

    async def execute(self, secret: str) -> None:
        """Выход идемпотентен: неизвестная или уже удалённая сессия не ошибка."""
        if not secret:
            return
        id_hash = hash_token(secret)
        session = await self._sessions.get(id_hash)
        if session is None:
            return
        async with self._uow.begin():
            await self._sessions.delete(id_hash)
            await self._audit.record("auth.logout", actor_id=session.user_id)


class ListSessionsUC:
    def __init__(self, sessions: ISessionRepository, clock: Clock = utc_now) -> None:
        self._sessions = sessions
        self._clock = clock

    async def execute(self, user_id: str, current_id_hash: str | None) -> list[SessionInfo]:
        now = self._clock()
        found = [s for s in await self._sessions.list_for_user(user_id) if s.expires_at > now]
        return [SessionInfo(session=s, current=s.id_hash == current_id_hash) for s in found]


class RevokeSessionUC:
    def __init__(self, sessions: ISessionRepository, audit: IAuditLog, uow: IUnitOfWork) -> None:
        self._sessions = sessions
        self._audit = audit
        self._uow = uow

    async def execute(self, user_id: str, id_hash: str) -> None:
        """Чужая сессия неотличима от несуществующей: `forbidden` не раскрывает, что она есть."""
        owned = {s.id_hash for s in await self._sessions.list_for_user(user_id)}
        if id_hash not in owned:
            raise IdentityError(IdentityErrorCode.forbidden)
        async with self._uow.begin():
            await self._sessions.delete(id_hash)
            await self._audit.record("auth.session_revoked", actor_id=user_id, target=id_hash[:12])


class RevokeOtherSessionsUC:
    def __init__(self, sessions: ISessionRepository, audit: IAuditLog, uow: IUnitOfWork) -> None:
        self._sessions = sessions
        self._audit = audit
        self._uow = uow

    async def execute(self, user_id: str, current_id_hash: str) -> int:
        async with self._uow.begin():
            revoked = await self._sessions.delete_for_user(user_id, except_id_hash=current_id_hash)
            if revoked:
                await self._audit.record("auth.sessions_revoked", actor_id=user_id, details={"count": revoked})
        return revoked
