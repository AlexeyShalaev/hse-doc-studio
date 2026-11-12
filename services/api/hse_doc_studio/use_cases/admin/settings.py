"""Настройки установки в админке: регистрация и способы входа. Окружение побеждает, последний вход не отключается."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.approval_exemptions import ExemptionRulesError, describe_problems, parse_rules
from hse_doc_studio.core.identity.auth_settings import (
    KEY_APPROVAL_EXEMPTIONS,
    KEY_PASSKEYS_ENABLED,
    KEY_PASSWORD_ENABLED,
    KEY_REGISTRATION_DOMAINS,
    KEY_REGISTRATION_MODE,
    KEY_REQUIRE_APPROVAL,
    normalize_domains,
)
from hse_doc_studio.core.identity.entities import AuthSettings, OidcProvider, RegistrationMode
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.passkeys import IPasskeyRepository
from hse_doc_studio.core.identity.protocols import IOidcProviderRepository
from hse_doc_studio.core.identity.setting_source import SettingDescription
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.identity.auth_settings import AuthSettingsPatch, AuthSettingsService, UpdateAuthSettingsUC

REGISTRATION_KEYS = (KEY_REGISTRATION_MODE, KEY_REGISTRATION_DOMAINS, KEY_REQUIRE_APPROVAL, KEY_APPROVAL_EXEMPTIONS)
AUTH_KEYS = (KEY_PASSWORD_ENABLED, KEY_PASSKEYS_ENABLED)


@dataclass(frozen=True)
class SettingsGroupView:
    settings: AuthSettings
    descriptions: dict[str, SettingDescription]
    # Включённые провайдеры единого входа: для экрана «Способы входа».
    enabled_providers: int = 0
    # Ключи passkey установки по доменам, к которым они привязаны: предупреждение о смене адреса.
    passkey_domains: dict[str, int] | None = None


async def ensure_login_method_remains(
    settings: AuthSettingsService, providers: Sequence[OidcProvider], *, password_enabled: bool | None = None
) -> None:
    """После изменения войти должен мочь хоть кто-то: по паролю или через включённого провайдера."""
    effective = password_enabled if password_enabled is not None else (await settings.effective()).password_enabled
    if not effective and not any(p.enabled for p in providers):
        raise IdentityError(IdentityErrorCode.last_login_method)


class GetAuthGroupUC:
    def __init__(
        self, service: AuthSettingsService, oidc: IOidcProviderRepository, passkeys: IPasskeyRepository | None = None
    ) -> None:
        self._service = service
        self._oidc = oidc
        self._passkeys = passkeys

    async def registration(self, actor: Actor) -> SettingsGroupView:
        require_admin(actor)
        return await self._group(REGISTRATION_KEYS)

    async def methods(self, actor: Actor) -> SettingsGroupView:
        require_admin(actor)
        view = await self._group(AUTH_KEYS)
        if self._passkeys is None:
            return view
        return SettingsGroupView(
            settings=view.settings,
            descriptions=view.descriptions,
            enabled_providers=view.enabled_providers,
            passkey_domains=await self._passkeys.count_by_rp_id(),
        )

    async def _group(self, keys: Sequence[str]) -> SettingsGroupView:
        view = await self._service.view()
        return SettingsGroupView(
            settings=view.settings,
            descriptions={key: await self._service.describe(key) for key in keys},
            enabled_providers=len(await self._oidc.list(only_enabled=True)),
        )


class UpdateRegistrationUC:
    def __init__(self, update: UpdateAuthSettingsUC, group: GetAuthGroupUC) -> None:
        self._update = update
        self._group = group

    async def execute(
        self,
        actor: Actor,
        *,
        mode: RegistrationMode | None,
        domains: Sequence[str] | None,
        require_approval: bool | None,
        approval_exemptions: Sequence[str] | None = None,
    ) -> SettingsGroupView:
        admin_id = require_admin(actor)
        exemptions = _strict_exemptions(approval_exemptions)
        current = (await self._group.registration(actor)).settings
        if (mode or current.registration_mode) is RegistrationMode.domains and not (
            current.registration_domains if domains is None else normalize_domains(list(domains))
        ):
            raise IdentityError(
                IdentityErrorCode.forbidden,
                localized_error(
                    "Для режима по доменам укажите хотя бы один домен.",
                    "Domain mode needs at least one domain.",
                ),
            )
        await self._update.execute(
            admin_id,
            AuthSettingsPatch(
                registration_mode=mode,
                registration_domains=domains,
                require_approval=require_approval,
                approval_exemptions=exemptions,
            ),
        )
        return await self._group.registration(actor)


def _strict_exemptions(lines: Sequence[str] | None) -> tuple[str, ...] | None:
    """Плохие строки отклоняются все сразу, с номером и причиной: молча выбросить правило админа нельзя."""
    if lines is None:
        return None
    try:
        return parse_rules(lines)
    except ExemptionRulesError as error:
        raise IdentityError(
            IdentityErrorCode.input_invalid,
            localized_error(
                describe_problems(error.problems, too_many=error.too_many, lang="ru"),
                describe_problems(error.problems, too_many=error.too_many, lang="en"),
            ),
        ) from error


class UpdateAuthMethodsUC:
    def __init__(
        self,
        update: UpdateAuthSettingsUC,
        service: AuthSettingsService,
        oidc: IOidcProviderRepository,
        group: GetAuthGroupUC,
    ) -> None:
        self._update = update
        self._service = service
        self._oidc = oidc
        self._group = group

    async def execute(
        self, actor: Actor, *, password_enabled: bool | None, passkeys_enabled: bool | None = None
    ) -> SettingsGroupView:
        """Passkey не считается способом входа установки: новый человек не может завести ключ, не войдя иначе."""
        admin_id = require_admin(actor)
        if password_enabled is False and not (await self._service.describe(KEY_PASSWORD_ENABLED)).locked:
            await ensure_login_method_remains(
                self._service, await self._oidc.list(only_enabled=True), password_enabled=False
            )
        await self._update.execute(
            admin_id, AuthSettingsPatch(password_enabled=password_enabled, passkeys_enabled=passkeys_enabled)
        )
        return await self._group.methods(actor)
