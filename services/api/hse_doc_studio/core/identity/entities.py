"""Сущности identity: пользователь, сессия, персональный токен, разовые токены, приглашения.

Секреты (сессии, токены) в сущностях хранятся только хешем sha256; сам секрет существует в
момент выдачи и отдаётся один раз.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class UserStatus(StrEnum):
    active = "active"
    pending_verification = "pending_verification"
    pending_approval = "pending_approval"
    disabled = "disabled"


class RegistrationMode(StrEnum):
    """Кто может зарегистрироваться; значения совпадают с `RegistrationMode` контракта."""

    open = "open"
    domains = "domains"
    invite = "invite"
    closed = "closed"


class TokenScope(StrEnum):
    api = "api"
    git_read = "git:read"
    git_write = "git:write"


class AuthTokenKind(StrEnum):
    """Разовые токены из писем и ссылок."""

    verify_email = "verify_email"
    reset_password = "reset_password"  # noqa: S105 — вид токена, не пароль
    setup = "setup"


@dataclass(frozen=True)
class User:
    id: str
    email: str
    # Ключ уникальности: `normalize_email(email)`.
    email_normalized: str
    name: str
    status: UserStatus
    created_at: datetime
    email_verified: bool = False
    is_instance_admin: bool = False
    locale: str | None = None
    last_login_at: datetime | None = None

    @property
    def can_sign_in(self) -> bool:
        return self.status is UserStatus.active


@dataclass(frozen=True)
class UserIdentity:
    """Внешняя учётная запись (OIDC): пара (provider, subject) уникальна."""

    user_id: str
    provider: str
    subject: str
    email: str | None = None
    email_verified: bool = False


@dataclass(frozen=True)
class Session:
    id_hash: str
    user_id: str
    # Токен CSRF привязан к строке сессии и в ответах отдаётся вместе с ней.
    csrf_token: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    ip: str | None = None
    user_agent: str = ""


@dataclass(frozen=True)
class ApiToken:
    id: str
    user_id: str
    name: str
    token_hash: str
    # Первые символы для опознания в списке.
    prefix: str
    scopes: frozenset[TokenScope]
    created_at: datetime
    expires_at: datetime | None = None
    last_used_at: datetime | None = None


@dataclass(frozen=True)
class AuthToken:
    token_hash: str
    kind: AuthTokenKind
    user_id: str | None
    expires_at: datetime
    used_at: datetime | None = None


@dataclass(frozen=True)
class RegistrationInvite:
    token_hash: str
    # Пусто: приглашение на любой адрес.
    email: str | None
    created_by: str
    expires_at: datetime
    used_at: datetime | None = None


@dataclass(frozen=True)
class AuthSettings:
    """Настройки входа установки; хранятся в instance_settings."""

    registration_mode: RegistrationMode = RegistrationMode.invite
    registration_domains: tuple[str, ...] = field(default_factory=tuple)
    require_approval: bool = False
    password_enabled: bool = True
