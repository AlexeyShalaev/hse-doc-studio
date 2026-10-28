"""Шаги мастера после администратора: режим регистрации и завершение."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.auth_settings import (
    KEY_PASSWORD_ENABLED,
    KEY_REGISTRATION_DOMAINS,
    KEY_REGISTRATION_MODE,
    KEY_REQUIRE_APPROVAL,
)
from hse_doc_studio.core.identity.entities import RegistrationMode
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog, IOidcProviderRepository
from hse_doc_studio.use_cases.identity.auth_settings import AuthSettingsPatch, AuthSettingsService, UpdateAuthSettingsUC
from hse_doc_studio.use_cases.server_setup.state import SetupStateService


@dataclass(frozen=True)
class InitialSettings:
    registration_mode: RegistrationMode
    registration_domains: Sequence[str]
    require_approval: bool
    password_enabled: bool


class ApplyInitialSettingsUC:
    def __init__(
        self,
        service: AuthSettingsService,
        update: UpdateAuthSettingsUC,
        oidc: IOidcProviderRepository,
        state: SetupStateService,
    ) -> None:
        self._service = service
        self._update = update
        self._oidc = oidc
        self._state = state

    async def execute(self, admin_id: str, settings: InitialSettings) -> None:
        """Ключи, заданные окружением, пропускаются (в мастере они только для чтения), остальные записываются."""
        locked = (await self._service.view()).locked
        password_off = not settings.password_enabled and KEY_PASSWORD_ENABLED not in locked
        if password_off and not await self._oidc.list(only_enabled=True):
            # Без пароля и без единого входа через провайдера в установку не войти никому, и админу тоже.
            raise IdentityError(
                IdentityErrorCode.forbidden,
                localized_error(
                    "Нельзя выключить вход по паролю, пока не подключён единый вход.",
                    "Password sign-in cannot be turned off until single sign-on is connected.",
                ),
            )
        domains = settings.registration_domains if settings.registration_mode is RegistrationMode.domains else []
        await self._update.execute(
            admin_id,
            AuthSettingsPatch(
                registration_mode=None if KEY_REGISTRATION_MODE in locked else settings.registration_mode,
                registration_domains=None if KEY_REGISTRATION_DOMAINS in locked else domains,
                require_approval=None if KEY_REQUIRE_APPROVAL in locked else settings.require_approval,
                password_enabled=None if KEY_PASSWORD_ENABLED in locked else settings.password_enabled,
            ),
        )
        await self._state.mark_settings_done()


class CompleteSetupUC:
    def __init__(self, state: SetupStateService, audit: IAuditLog) -> None:
        self._state = state
        self._audit = audit

    async def execute(self, admin_id: str) -> None:
        """До завершения регистрация идёт по умолчанию «по приглашению», завершение ничего не открывает."""
        await self._state.mark_completed()
        await self._audit.record("setup.completed", actor_id=admin_id)
