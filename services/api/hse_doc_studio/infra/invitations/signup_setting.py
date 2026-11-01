"""S12: даёт ли приглашение в проект право зарегистрироваться в режиме «только по приглашению».

Значение общее с настройками общего доступа трека links: ключ установки
`registration.project_invites_allow_signup` (по умолчанию true) и окружение
`HSE_STUDIO__AUTH__PROJECT_INVITES_ALLOW_SIGNUP`, которое сильнее значения админа. Разбор один:
`core.access.sharing_policy.effective_instance_sharing`, поэтому страница «Общий доступ» и приглашения
не расходятся.
"""

from __future__ import annotations

from hse_doc_studio.core.access.sharing_policy import SharingEnvOverrides, effective_instance_sharing
from hse_doc_studio.core.identity.protocols import IInstanceSettingsRepository


class ProjectInviteSignupSetting:
    def __init__(self, settings: IInstanceSettingsRepository, env: SharingEnvOverrides) -> None:
        self._settings = settings
        self._env = env

    async def __call__(self) -> bool:
        values = await self._settings.get_all()
        return effective_instance_sharing(values, self._env).project_invites_allow_signup
