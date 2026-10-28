"""Настройки входа установки: чтение с учётом окружения и правка админом."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from hse_doc_studio.core.identity.auth_settings import (
    KEY_PASSWORD_ENABLED,
    KEY_REGISTRATION_DOMAINS,
    KEY_REGISTRATION_MODE,
    KEY_REQUIRE_APPROVAL,
    AuthEnvOverrides,
    effective_auth_settings,
    normalize_domains,
)
from hse_doc_studio.core.identity.entities import AuthSettings, RegistrationMode
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode, message_for
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository

SOURCE_ADMIN = "admin"


@dataclass(frozen=True)
class AuthSettingsView:
    settings: AuthSettings
    # Ключи, заданные окружением: в интерфейсе только для чтения.
    locked: frozenset[str]


class AuthSettingsService:
    def __init__(self, repo: IInstanceSettingsRepository, env: AuthEnvOverrides | None = None) -> None:
        self._repo = repo
        self._env = env or AuthEnvOverrides()

    async def view(self) -> AuthSettingsView:
        return AuthSettingsView(
            settings=effective_auth_settings(await self._repo.get_all(), self._env), locked=self._env.locked_keys()
        )

    async def effective(self) -> AuthSettings:
        return (await self.view()).settings


@dataclass(frozen=True)
class AuthSettingsPatch:
    """Меняется только заданное (не None)."""

    registration_mode: RegistrationMode | None = None
    registration_domains: Sequence[str] | None = None
    require_approval: bool | None = None
    password_enabled: bool | None = None

    def values(self) -> dict[str, object]:
        pairs: dict[str, object | None] = {
            KEY_REGISTRATION_MODE: self.registration_mode.value if self.registration_mode else None,
            KEY_REGISTRATION_DOMAINS: (
                list(normalize_domains(list(self.registration_domains)))
                if self.registration_domains is not None
                else None
            ),
            KEY_REQUIRE_APPROVAL: self.require_approval,
            KEY_PASSWORD_ENABLED: self.password_enabled,
        }
        return {key: value for key, value in pairs.items() if value is not None}


class UpdateAuthSettingsUC:
    def __init__(self, service: AuthSettingsService, repo: IInstanceSettingsRepository, audit: IAuditLog) -> None:
        self._service = service
        self._repo = repo
        self._audit = audit

    async def execute(self, actor_id: str, patch: AuthSettingsPatch) -> AuthSettingsView:
        """Заданный окружением ключ не правится: отказ целиком, ничего не записывается."""
        values = patch.values()
        view = await self._service.view()
        if locked := sorted(set(values) & view.locked):
            raise IdentityError(
                IdentityErrorCode.setting_locked,
                f"{message_for(IdentityErrorCode.setting_locked)} ({', '.join(locked)})",
            )
        for key, value in values.items():
            await self._repo.set(key, value, source=SOURCE_ADMIN)
        if values:
            await self._audit.record("settings.auth_update", actor_id=actor_id, details=values)
        return await self._service.view()
