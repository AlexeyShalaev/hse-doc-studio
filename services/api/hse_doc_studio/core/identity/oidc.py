"""Вход через OIDC: Authorization Code с PKCE. Модель, порты и правила без ввода-вывода."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from urllib.parse import urlsplit

DEFAULT_NEXT = "/"
_MAX_NEXT = 2048


class OidcErrorCode(StrEnum):
    """Почему вход не удался. Клиент получает `oidc_<код>` на странице /auth/error, подробности только в журнале."""

    provider_unknown = "provider_unknown"
    provider_denied = "provider_denied"
    state_invalid = "state_invalid"
    state_expired = "state_expired"
    discovery_failed = "discovery_failed"
    token_exchange_failed = "token_exchange_failed"  # noqa: S105 — код ошибки, не токен
    token_invalid = "token_invalid"  # noqa: S105 — код ошибки, не токен
    not_linked = "not_linked"
    account_denied = "account_denied"
    # Почта у провайдера не подтверждена или её нет: по ней нельзя ни связать аккаунт, ни завести новый.
    email_unverified = "email_unverified"
    # Аккаунт с этой почтой есть, но его почта не подтверждена: сначала войти по паролю и привязать вход из профиля.
    link_required = "link_required"
    # Режим регистрации не пускает нового человека (закрыта, по приглашению, чужой домен).
    registration_denied = "registration_denied"
    pending_approval = "pending_approval"
    identity_taken = "identity_taken"


class OidcLoginError(Exception):
    def __init__(self, code: OidcErrorCode, detail: str = "") -> None:
        super().__init__(f"{code.value}: {detail}" if detail else code.value)
        self.code = code
        self.detail = detail

    @property
    def public_code(self) -> str:
        return f"oidc_{self.code.value}"


@dataclass(frozen=True)
class OidcProviderConfig:
    """Провайдер в рабочем виде: секрет уже расшифрован, окружение это или таблица, вызывающему всё равно."""

    id: str
    label: str
    issuer: str
    client_id: str
    client_secret: str
    scopes: str = "openid email profile"
    auto_provision: bool = False

    def __repr__(self) -> str:
        return f"OidcProviderConfig(id={self.id!r}, issuer={self.issuer!r})"


@dataclass(frozen=True)
class OidcClaims:
    """Проверенные утверждения ID-токена."""

    provider_id: str
    subject: str
    email: str | None
    email_verified: bool
    name: str | None


@dataclass(frozen=True)
class OidcLoginState:
    """Что помним между уходом к провайдеру и возвратом; лежит в подписанной cookie."""

    provider_id: str
    state: str
    nonce: str
    code_verifier: str
    redirect_uri: str
    next_path: str
    expires_at: datetime
    # Не None, когда вошедший человек привязывает провайдера к своему аккаунту, а не входит.
    link_user_id: str | None = None


@dataclass(frozen=True)
class OidcAuthorizeRequest:
    provider: OidcProviderConfig
    redirect_uri: str
    state: str
    nonce: str
    code_challenge: str


class IOidcProviderCatalog(Protocol):
    async def get(self, provider_id: str) -> OidcProviderConfig | None:
        """Включённый провайдер либо None."""
        ...

    async def list_enabled(self) -> list[tuple[str, str]]:
        """Пары (id, название) для кнопок на странице входа."""
        ...


class IOidcClient(Protocol):
    async def authorize_url(self, request: OidcAuthorizeRequest) -> str:
        """Бросает OidcLoginError(discovery_failed), если провайдер недоступен или его описание негодно."""
        ...

    async def exchange(
        self, provider: OidcProviderConfig, *, code: str, code_verifier: str, redirect_uri: str, nonce: str
    ) -> OidcClaims:
        """Обменять код на токены и проверить ID-токен (подпись, iss, aud, exp, nonce)."""
        ...


class IOidcStateCodec(Protocol):
    def seal(self, state: OidcLoginState) -> str: ...
    def open(self, sealed: str) -> OidcLoginState | None:
        """None, если подпись не сходится или значение повреждено."""
        ...


def safe_next(value: str | None) -> str:
    """Куда вернуть человека после входа: только путь этого же сайта, иначе главная.

    Отвергается всё, что браузер может принять за другой сайт: `//host`, `/\\host`, схема, управляющие символы.
    """
    if not value or len(value) > _MAX_NEXT or not value.startswith("/"):
        return DEFAULT_NEXT
    if value.startswith(("//", "/\\")) or "\\" in value:
        return DEFAULT_NEXT
    if any(ord(char) < 0x20 or ord(char) == 0x7F or char.isspace() for char in value):
        return DEFAULT_NEXT
    parts = urlsplit(value)
    if parts.scheme or parts.netloc:
        return DEFAULT_NEXT
    return value
