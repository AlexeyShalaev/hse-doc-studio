"""Настройки входа установки: ключи в instance_settings и разбор значений с безопасными умолчаниями."""

from __future__ import annotations

from collections.abc import Mapping

from hse_doc_studio.core.identity.entities import AuthSettings, RegistrationMode

KEY_REGISTRATION_MODE = "auth.registration_mode"
KEY_REGISTRATION_DOMAINS = "auth.registration_domains"
KEY_REQUIRE_APPROVAL = "auth.require_approval"
KEY_PASSWORD_ENABLED = "auth.password_enabled"  # noqa: S105 — имя ключа настройки, не пароль


def auth_settings_from(values: Mapping[str, object]) -> AuthSettings:
    """Непонятное значение не открывает вход: регистрация падает на «по приглашению», пароль остаётся включённым."""
    raw_mode = values.get(KEY_REGISTRATION_MODE)
    try:
        mode = RegistrationMode(raw_mode) if isinstance(raw_mode, str) else RegistrationMode.invite
    except ValueError:
        mode = RegistrationMode.invite
    domains = values.get(KEY_REGISTRATION_DOMAINS)
    password_enabled = values.get(KEY_PASSWORD_ENABLED)
    approval = values.get(KEY_REQUIRE_APPROVAL)
    return AuthSettings(
        registration_mode=mode,
        registration_domains=tuple(str(d) for d in domains) if isinstance(domains, list) else (),
        require_approval=approval if isinstance(approval, bool) else False,
        password_enabled=password_enabled if isinstance(password_enabled, bool) else True,
    )
