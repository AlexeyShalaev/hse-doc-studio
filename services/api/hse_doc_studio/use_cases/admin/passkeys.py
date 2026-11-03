"""Passkey людей в админке: сколько ключей у человека и сброс всех его ключей (без доступа к самим ключам)."""

from __future__ import annotations

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.passkeys import IPasskeyRepository, Passkey
from hse_doc_studio.core.identity.protocols import IAuditLog, IUserRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.admin.users import require_admin


class ListUserPasskeysUC:
    def __init__(self, users: IUserRepository, passkeys: IPasskeyRepository) -> None:
        self._users = users
        self._passkeys = passkeys

    async def execute(self, actor: Actor, user_id: str) -> list[Passkey]:
        require_admin(actor)
        if await self._users.get(user_id) is None:
            raise IdentityError(IdentityErrorCode.not_found)
        return await self._passkeys.list_for_user(user_id)


class ResetUserPasskeysUC:
    """Человек потерял устройство или ключ скомпрометирован: админ удаляет все его ключи разом.

    Сессии не закрываются (их закрывает отдельное действие), пароль и единый вход не трогаются. Если у человека
    не останется способа войти, админ выдаёт ссылку сброса пароля.
    """

    def __init__(
        self, users: IUserRepository, passkeys: IPasskeyRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> None:
        self._users = users
        self._passkeys = passkeys
        self._audit = audit
        self._uow = uow

    async def execute(self, actor: Actor, user_id: str) -> int:
        admin_id = require_admin(actor)
        async with self._uow.begin():
            if await self._users.get_for_update(user_id) is None:
                raise IdentityError(IdentityErrorCode.not_found)
            removed = await self._passkeys.delete_for_user(user_id)
            await self._audit.record(
                "admin.passkeys_reset", actor_id=admin_id, target=user_id, details={"count": removed}
            )
        return removed
