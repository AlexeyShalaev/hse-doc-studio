"""Смена пароля залогиненным пользователем."""

from __future__ import annotations

from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.passwords import check_password
from hse_doc_studio.core.identity.protocols import (
    IAuditLog,
    ICredentialRepository,
    IPasswordHasher,
    ISessionRepository,
    IUserRepository,
)
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
    ) -> None:
        self._users = users
        self._credentials = credentials
        self._sessions = sessions
        self._hasher = hasher
        self._audit = audit
        self._uow = uow

    async def execute(self, user_id: str, current_id_hash: str, current_password: str, new_password: str) -> int:
        """Меняет пароль и закрывает все остальные сессии; возвращает, сколько их закрыто."""
        user = await self._users.get(user_id)
        stored = await self._credentials.get_hash(user_id)
        if user is None or stored is None or not self._hasher.verify(current_password, stored):
            await self._audit.record("auth.password_change_failed", actor_id=user_id)
            raise IdentityError(IdentityErrorCode.invalid_credentials)
        check_password(new_password, user.email)
        new_hash = self._hasher.hash(new_password)
        async with self._uow.begin():
            await self._credentials.set_hash(user_id, new_hash)
            revoked = await self._sessions.delete_for_user(user_id, except_id_hash=current_id_hash)
            await self._audit.record("auth.password_changed", actor_id=user_id, details={"revoked_sessions": revoked})
        return revoked
