"""Состояние мастера первого запуска: что уже сделано и завершён ли он."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from hse_doc_studio.core.identity.auth_settings import AuthEnvOverrides
from hse_doc_studio.core.identity.protocols import IInstanceSettingsRepository, IUserRepository
from hse_doc_studio.use_cases.server_setup.token import SetupToken

KEY_SETUP_COMPLETED = "setup.completed"
KEY_SETUP_SETTINGS_DONE = "setup.settings_done"
SOURCE_WIZARD = "wizard"

SetupStep = Literal["admin", "settings"]
SetupStateName = Literal["needs_admin", "ready"]


@dataclass(frozen=True)
class SetupStatus:
    state: SetupStateName
    token_required: bool
    steps_done: tuple[SetupStep, ...]


class SetupStateService:
    """Завершённость мастера хранится в `instance_settings`; завершённое не откатывается, поэтому «да» кэшируется."""

    def __init__(self, settings: IInstanceSettingsRepository) -> None:
        self._settings = settings
        self._completed = False

    async def is_completed(self) -> bool:
        if not self._completed:
            self._completed = (await self._settings.get_all()).get(KEY_SETUP_COMPLETED) is True
        return self._completed

    async def mark_completed(self) -> None:
        await self._settings.set(KEY_SETUP_COMPLETED, True, source=SOURCE_WIZARD)
        self._completed = True

    async def mark_settings_done(self) -> None:
        await self._settings.set(KEY_SETUP_SETTINGS_DONE, True, source=SOURCE_WIZARD)


class GetSetupStatusUC:
    def __init__(
        self,
        state: SetupStateService,
        settings: IInstanceSettingsRepository,
        users: IUserRepository,
        token: SetupToken,
        env: AuthEnvOverrides,
    ) -> None:
        self._state = state
        self._settings = settings
        self._users = users
        self._token = token
        self._env = env

    async def execute(self) -> SetupStatus:
        if await self._state.is_completed():
            return SetupStatus("ready", False, ("admin", "settings"))
        has_admin = await self._users.count() > 0
        values = await self._settings.get_all()
        # Режим регистрации из окружения заменяет шаг мастера: выбирать нечего.
        settings_done = values.get(KEY_SETUP_SETTINGS_DONE) is True or self._env.registration_mode is not None
        steps: list[SetupStep] = []
        if has_admin:
            steps.append("admin")
        if settings_done:
            steps.append("settings")
        return SetupStatus("needs_admin", self._token.required and not has_admin, tuple(steps))
