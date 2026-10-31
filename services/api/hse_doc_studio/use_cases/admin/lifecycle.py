"""Жизненный цикл данных: удаление человека, его выгрузка, сроки хранения установки."""

from __future__ import annotations

from collections.abc import Mapping

from hse_doc_studio.core.access.entities import Actor, ActorKind
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.lifecycle import IUserLifecycle, RetentionPolicy, pseudonym_for
from hse_doc_studio.core.identity.protocols import IAuditLog, IUserRepository
from hse_doc_studio.core.jobs.runners import IUserRunnerRevoker
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.admin.last_admin import ensure_admin_remains
from hse_doc_studio.use_cases.admin.users import require_admin


class DeleteUserUC:
    """Удаление окончательное и только после отключения (отключение обратимо, удаление нет).

    Пока человек единственный владелец проекта или организации, удалить его нельзя. Журнал не стирается:
    id человека в событиях заменяется псевдонимом, личные поля из деталей убираются."""

    def __init__(
        self,
        users: IUserRepository,
        lifecycle: IUserLifecycle,
        audit: IAuditLog,
        uow: IUnitOfWork,
        runners: IUserRunnerRevoker | None = None,
    ) -> None:
        self._users = users
        self._lifecycle = lifecycle
        self._audit = audit
        self._uow = uow
        self._runners = runners

    async def execute(self, actor: Actor, user_id: str) -> None:
        admin_id = require_admin(actor)
        if user_id == admin_id:
            raise IdentityError(IdentityErrorCode.forbidden)
        async with self._uow.begin():
            user = await self._users.get_for_update(user_id)
            if user is None:
                raise IdentityError(IdentityErrorCode.not_found)
            if user.can_sign_in:
                raise IdentityError(IdentityErrorCode.user_not_disabled)
            if (await self._lifecycle.blockers(user_id)).any:
                raise IdentityError(IdentityErrorCode.user_has_projects)
            await ensure_admin_remains(self._users, user, None)
            pseudonym = pseudonym_for(user_id)
            # Личные раннеры человека переживают его как записи журнала, но работать больше не могут.
            runners = await self._runners.revoke_all_of_user(user_id) if self._runners is not None else 0
            report = await self._lifecycle.erase(user_id, pseudonym)
            await self._audit.record(
                "admin.user_deleted",
                actor_id=admin_id,
                target=pseudonym,
                details={
                    "audit_anonymized": report.audit_anonymized,
                    "api_tokens": report.api_tokens,
                    "sessions": report.sessions,
                    "settings": report.settings,
                    "runners": runners,
                },
            )


class ExportMyDataUC:
    """Выгрузка всего, что установка хранит о самом человеке; чужую выгрузку не получает никто."""

    def __init__(self, lifecycle: IUserLifecycle, audit: IAuditLog) -> None:
        self._lifecycle = lifecycle
        self._audit = audit

    async def execute(self, actor: Actor) -> Mapping[str, object]:
        # У гостя по ссылке тоже есть id (сессии), но выгружать нечего: только вошедший человек.
        if actor.kind is not ActorKind.user or actor.id is None:
            raise IdentityError(IdentityErrorCode.auth_required)
        data = await self._lifecycle.export(actor.id)
        await self._audit.record("account.data_exported", actor_id=actor.id, target=actor.id)
        return data


class GetRetentionUC:
    def __init__(self, policy: RetentionPolicy) -> None:
        self._policy = policy

    async def execute(self, actor: Actor) -> RetentionPolicy:
        require_admin(actor)
        return self._policy
