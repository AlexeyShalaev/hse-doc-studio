"""S12: даёт ли приглашение в проект право зарегистрироваться в режиме «только по приглашению».

Ключ установки `registration.project_invites_allow_signup` (по умолчанию true); окружение
`HSE_STUDIO__AUTH__PROJECT_INVITES_ALLOW_SIGNUP` сильнее значения админа. Запись ключа и UI делает трек links.
"""

from __future__ import annotations

import os

from hse_doc_studio.core.identity.protocols import IInstanceSettingsRepository

SETTING_KEY = "registration.project_invites_allow_signup"
ENV_NAME = "HSE_STUDIO__AUTH__PROJECT_INVITES_ALLOW_SIGNUP"
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


class ProjectInviteSignupSetting:
    def __init__(self, settings: IInstanceSettingsRepository) -> None:
        self._settings = settings

    async def __call__(self) -> bool:
        raw = os.environ.get(ENV_NAME)
        if raw is not None and raw.strip().lower() in _TRUE | _FALSE:
            return raw.strip().lower() in _TRUE
        value = (await self._settings.get_all()).get(SETTING_KEY)
        return value if isinstance(value, bool) else True
