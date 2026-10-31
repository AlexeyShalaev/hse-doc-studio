"""Общий доступ в настройках установки: ссылки на проекты, предел роли по ссылке, регистрация по приглашению в проект.

Ключ `registration.project_invites_allow_signup` читает трек приглашений; страница и API здесь, чтобы раздел
«Общий доступ» в админке был один. Значения окружения побеждают и блокируют правку (`409 setting_locked`).
"""

from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.access.links import LinkRole
from hse_doc_studio.core.access.sharing_policy import (
    KEY_LINKS_ENABLED,
    KEY_MAX_LINK_ROLE,
    KEY_PROJECT_INVITES_ALLOW_SIGNUP,
    SHARING_KEYS,
    InstanceSharing,
    SharingEnvOverrides,
    effective_instance_sharing,
)
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode, message_for
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository
from hse_doc_studio.core.identity.setting_source import SettingDescription, describe_setting
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.identity.auth_settings import SOURCE_ADMIN


@dataclass(frozen=True)
class SharingSettingsView:
    settings: InstanceSharing
    descriptions: dict[str, SettingDescription]


@dataclass(frozen=True)
class SharingSettingsPatch:
    links_enabled: bool | None = None
    max_link_role: LinkRole | None = None
    project_invites_allow_signup: bool | None = None


class GetSharingSettingsUC:
    def __init__(self, repo: IInstanceSettingsRepository, env: SharingEnvOverrides) -> None:
        self._repo = repo
        self._env = env

    async def execute(self, actor: Actor) -> SharingSettingsView:
        require_admin(actor)
        stored = await self._repo.get_all()
        locked = self._env.locked_keys()
        return SharingSettingsView(
            effective_instance_sharing(stored, self._env),
            {key: describe_setting(key, stored=stored, locked=locked) for key in SHARING_KEYS},
        )


class UpdateSharingSettingsUC:
    def __init__(
        self,
        repo: IInstanceSettingsRepository,
        env: SharingEnvOverrides,
        audit: IAuditLog,
        uow: IUnitOfWork,
        read: GetSharingSettingsUC,
    ) -> None:
        self._repo = repo
        self._env = env
        self._audit = audit
        self._uow = uow
        self._read = read

    async def execute(self, actor: Actor, patch: SharingSettingsPatch) -> SharingSettingsView:
        admin_id = require_admin(actor)
        values: dict[str, object] = {}
        if patch.links_enabled is not None:
            values[KEY_LINKS_ENABLED] = patch.links_enabled
        if patch.max_link_role is not None:
            values[KEY_MAX_LINK_ROLE] = patch.max_link_role.value
        if patch.project_invites_allow_signup is not None:
            values[KEY_PROJECT_INVITES_ALLOW_SIGNUP] = patch.project_invites_allow_signup
        if locked := sorted(set(values) & self._env.locked_keys()):
            raise IdentityError(
                IdentityErrorCode.setting_locked,
                f"{message_for(IdentityErrorCode.setting_locked)} ({', '.join(locked)})",
            )
        if values:
            async with self._uow.begin():
                for key, value in values.items():
                    await self._repo.set(key, value, source=SOURCE_ADMIN)
                await self._audit.record("settings.sharing_update", actor_id=admin_id, details=values)
        return await self._read.execute(actor)
