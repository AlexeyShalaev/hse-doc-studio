"""Настройки входа установки: ключи в instance_settings и разбор значений с безопасными умолчаниями."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from hse_doc_studio.core.identity.entities import AuthSettings, RegistrationMode
from hse_doc_studio.core.identity.normalize import normalize_domain

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
        registration_domains=normalize_domains([str(d) for d in domains]) if isinstance(domains, list) else (),
        require_approval=approval if isinstance(approval, bool) else False,
        password_enabled=password_enabled if isinstance(password_enabled, bool) else True,
    )


@dataclass(frozen=True)
class AuthEnvOverrides:
    """Значения из окружения: заданное (не None) побеждает БД, в интерфейсе показывается только для чтения."""

    registration_mode: RegistrationMode | None = None
    registration_domains: tuple[str, ...] | None = None
    require_approval: bool | None = None
    password_enabled: bool | None = None

    def locked_keys(self) -> frozenset[str]:
        pairs = (
            (KEY_REGISTRATION_MODE, self.registration_mode),
            (KEY_REGISTRATION_DOMAINS, self.registration_domains),
            (KEY_REQUIRE_APPROVAL, self.require_approval),
            (KEY_PASSWORD_ENABLED, self.password_enabled),
        )
        return frozenset(key for key, value in pairs if value is not None)


def effective_auth_settings(values: Mapping[str, object], env: AuthEnvOverrides) -> AuthSettings:
    """Настройки из БД, поверх которых лежат заданные в окружении. Само окружение в БД не пишется:
    убрали переменную, и снова действует значение админа."""
    stored = auth_settings_from(values)
    return replace(
        stored,
        registration_mode=env.registration_mode if env.registration_mode is not None else stored.registration_mode,
        registration_domains=(
            normalize_domains(env.registration_domains)
            if env.registration_domains is not None
            else stored.registration_domains
        ),
        require_approval=env.require_approval if env.require_approval is not None else stored.require_approval,
        password_enabled=env.password_enabled if env.password_enabled is not None else stored.password_enabled,
    )


def normalize_domains(domains: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Домены без `@`, в нижнем регистре, без пустых и повторов, порядок сохраняется."""
    seen: dict[str, None] = {}
    for raw in domains:
        domain = normalize_domain(raw)
        if domain:
            seen.setdefault(domain)
    return tuple(seen)
