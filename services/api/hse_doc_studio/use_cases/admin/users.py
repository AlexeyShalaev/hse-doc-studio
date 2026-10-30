"""Люди установки: список, отключение, роль админа, отзыв сессий, одобрение регистраций (без содержимого проектов)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.entities import User, UserFacets, UserListing, UserPickQuery, UserQuery, UserStatus
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog, ISessionRepository, IUserDirectory, IUserRepository
from hse_doc_studio.core.listing import Found, Picked
from hse_doc_studio.core.orgs.entities import UserOrgQuery, UserOrgView
from hse_doc_studio.core.orgs.protocols import IOrgRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.admin.last_admin import ensure_admin_remains


def require_admin(actor: Actor) -> str:
    if not actor.is_instance_admin or actor.id is None:
        raise IdentityError(IdentityErrorCode.not_found)
    return actor.id


class ListUsersUC:
    def __init__(self, directory: IUserDirectory) -> None:
        self._directory = directory

    async def execute(self, actor: Actor, query: UserQuery) -> Found[UserListing]:
        require_admin(actor)
        return await self._directory.search(query)


class UserFacetsUC:
    """Счётчики на чипах статусов одним запросом вместо страницы на каждый статус."""

    def __init__(self, directory: IUserDirectory) -> None:
        self._directory = directory

    async def execute(self, actor: Actor, q: str | None) -> UserFacets:
        require_admin(actor)
        return await self._directory.facets(q)


class PickUsersUC:
    """Пикер людей для админа установки: он видит всех, поэтому охват не сужается."""

    def __init__(self, directory: IUserDirectory) -> None:
        self._directory = directory

    async def execute(self, actor: Actor, query: UserPickQuery) -> Picked[User]:
        require_admin(actor)
        return await self._directory.pick(query)


class ListUserOrgsUC:
    """Организации человека в его карточке: одним запросом, а не составом каждой организации."""

    def __init__(self, users: IUserRepository, orgs: IOrgRepository) -> None:
        self._users = users
        self._orgs = orgs

    async def execute(self, actor: Actor, user_id: str, query: UserOrgQuery) -> Found[UserOrgView]:
        require_admin(actor)
        if await self._users.get(user_id) is None:
            raise IdentityError(IdentityErrorCode.not_found)
        return await self._orgs.page_for_user(user_id, query)


class GetUserUC:
    def __init__(self, directory: IUserDirectory) -> None:
        self._directory = directory

    async def execute(self, actor: Actor, user_id: str) -> UserListing:
        require_admin(actor)
        listing = await self._directory.get(user_id)
        if listing is None:
            raise IdentityError(IdentityErrorCode.not_found)
        return listing


class _UserChange:
    """Общая часть изменений пользователя: свежая строка под блокировкой, защита последнего админа, аудит."""

    def __init__(self, users: IUserRepository, audit: IAuditLog, uow: IUnitOfWork) -> None:
        self._users = users
        self._audit = audit
        self._uow = uow

    async def _apply(self, actor: Actor, user_id: str, action: str, change: Callable[[User], User]) -> User:
        admin_id = require_admin(actor)
        async with self._uow.begin():
            before = await self._users.get_for_update(user_id)
            if before is None:
                raise IdentityError(IdentityErrorCode.not_found)
            after = change(before)
            if after == before:
                return before
            await ensure_admin_remains(self._users, before, after)
            await self._users.update(after)
            await self._after(after)
            await self._audit.record(action, actor_id=admin_id, target=user_id)
        return after

    async def _after(self, user: User) -> None:
        return None


class DisableUserUC(_UserChange):
    """Отключённый не входит: его сессии закрываются сразу. Данные и проекты остаются."""

    def __init__(
        self, users: IUserRepository, sessions: ISessionRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> None:
        super().__init__(users, audit, uow)
        self._sessions = sessions

    async def execute(self, actor: Actor, user_id: str) -> User:
        return await self._apply(actor, user_id, "admin.user_disabled", _disable)

    async def _after(self, user: User) -> None:
        await self._sessions.delete_for_user(user.id)


def _disable(user: User) -> User:
    return replace(user, status=UserStatus.disabled)


class EnableUserUC(_UserChange):
    async def execute(self, actor: Actor, user_id: str) -> User:
        return await self._apply(actor, user_id, "admin.user_enabled", _enable)


def _enable(user: User) -> User:
    # Включение возвращает отключённого; ожидающих одобрения и подтверждения оно не обходит.
    if user.status is not UserStatus.disabled:
        raise IdentityError(IdentityErrorCode.not_found)
    return replace(user, status=UserStatus.active)


class SetUserAdminUC(_UserChange):
    async def execute(self, actor: Actor, user_id: str, *, is_admin: bool) -> User:
        action = "admin.admin_granted" if is_admin else "admin.admin_revoked"
        return await self._apply(actor, user_id, action, lambda u: replace(u, is_instance_admin=is_admin))


class RevokeUserSessionsUC:
    def __init__(
        self, users: IUserRepository, sessions: ISessionRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._audit = audit
        self._uow = uow

    async def execute(self, actor: Actor, user_id: str) -> int:
        admin_id = require_admin(actor)
        if await self._users.get(user_id) is None:
            raise IdentityError(IdentityErrorCode.not_found)
        async with self._uow.begin():
            revoked = await self._sessions.delete_for_user(user_id)
            await self._audit.record(
                "admin.sessions_revoked", actor_id=admin_id, target=user_id, details={"count": revoked}
            )
        return revoked


class ListApprovalsUC:
    """Очередь регистраций, которые ждут решения админа."""

    def __init__(self, directory: IUserDirectory) -> None:
        self._directory = directory

    async def execute(self, actor: Actor, query: UserQuery) -> Found[UserListing]:
        """Фильтр статуса задаёт сама очередь: чужие статусы в ней не показываются."""
        require_admin(actor)
        return await self._directory.search(replace(query, statuses=(UserStatus.pending_approval,)))


class _Decision(_UserChange):
    async def _decide(self, actor: Actor, user_id: str, action: str, status: UserStatus) -> User:
        def change(user: User) -> User:
            # Решение принимается один раз: не ожидающий одобрения для очереди всё равно что отсутствует.
            if user.status is not UserStatus.pending_approval:
                raise IdentityError(IdentityErrorCode.not_found)
            return replace(user, status=status)

        return await self._apply(actor, user_id, action, change)


class ApproveUserUC(_Decision):
    async def execute(self, actor: Actor, user_id: str) -> User:
        return await self._decide(actor, user_id, "admin.user_approved", UserStatus.active)


class RejectUserUC(_Decision):
    """Отказ оставляет учётную запись отключённой: адрес остаётся занятым, повторно зарегистрироваться нельзя."""

    async def execute(self, actor: Actor, user_id: str) -> User:
        return await self._decide(actor, user_id, "admin.user_rejected", UserStatus.disabled)
