"""Смена пароля залогиненным пользователем."""

from __future__ import annotations

from hse_doc_studio.core.identity.entities import AuthTokenKind
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
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
from hse_doc_studio.core.uow import IUnitOfWork


class ChangePasswordUC:
    def __init__(
        self,
        users: IUserRepository,
        credentials: ICredentialRepository,
        sessions: ISessionRepository,
        hasher: IPasswordHasher,
        audit: IAuditLog,
        uow: IUnitOfWork,
        auth_tokens: IAuthTokenRepository,
        clock: Clock = utc_now,
    ) -> None:
        self._users = users
        self._credentials = credentials
        self._auth_tokens = auth_tokens
        self._clock = clock
        self._sessions = sessions
        self._hasher = hasher
        self._audit = audit
        self._uow = uow

    async def execute(
        self,
        user_id: str,
        current_id_hash: str,
        current_password: str,
        new_password: str,
        *,
        sign_out_others: bool = True,
    ) -> int:
        """Меняет пароль и по умолчанию закрывает все остальные сессии; возвращает, сколько их закрыто."""
        user = await self._users.get(user_id)
        stored = await self._credentials.get_hash(user_id)
        if user is None or stored is None or not self._hasher.verify(current_password, stored):
            await self._audit.record("auth.password_change_failed", actor_id=user_id)
            raise IdentityError(IdentityErrorCode.invalid_credentials)
        check_password(new_password, user.email)
        new_hash = self._hasher.hash(new_password)
        async with self._uow.begin():
            await self._credentials.set_hash(user_id, new_hash)
            # Ссылки сброса, выданные до смены пароля, больше не должны его перезаписать.
            await self._auth_tokens.invalidate_for_user(user_id, AuthTokenKind.reset_password, self._clock())
            revoked = (
                await self._sessions.delete_for_user(user_id, except_id_hash=current_id_hash) if sign_out_others else 0
            )
            await self._audit.record("auth.password_changed", actor_id=user_id, details={"revoked_sessions": revoked})
        return revoked
