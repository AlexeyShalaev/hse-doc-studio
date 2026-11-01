"""Защита последнего администратора установки: без него в админку не войти и не починить доступы."""

from __future__ import annotations

from hse_doc_studio.core.identity.entities import User
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IUserRepository


def _is_active_admin(user: User) -> bool:
    return user.is_instance_admin and user.can_sign_in


async def ensure_admin_remains(users: IUserRepository, before: User, after: User | None) -> None:
    """Вызывается в транзакции изменения пользователя (`after=None`: удаление) до записи.

    Если `before` был действующим админом, а после изменения им не будет, должен остаться другой действующий админ,
    иначе `IdentityError(last_admin)`. Строки админов блокируются до конца транзакции: двое админов, которые
    одновременно снимают права друг у друга, не оставят установку без админа.
    """
    if not _is_active_admin(before) or (after is not None and _is_active_admin(after)):
        return
    if await users.lock_active_admins() <= 1:
        raise IdentityError(IdentityErrorCode.last_admin)
