"""Настройки исходящей почты: ключи в instance_settings, пароль отдельно шифртекстом."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

SmtpSecurity = Literal["starttls", "tls", "none"]
SMTP_SECURITIES: tuple[SmtpSecurity, ...] = ("starttls", "tls", "none")

KEY_HOST = "smtp.host"
KEY_PORT = "smtp.port"
KEY_SECURITY = "smtp.security"
KEY_USERNAME = "smtp.username"
KEY_PASSWORD = "smtp.password"  # noqa: S105 — имя ключа настройки, не пароль
KEY_FROM_ADDRESS = "smtp.from_address"
KEY_FROM_NAME = "smtp.from_name"

SMTP_KEYS = (KEY_HOST, KEY_PORT, KEY_SECURITY, KEY_USERNAME, KEY_PASSWORD, KEY_FROM_ADDRESS, KEY_FROM_NAME)

DEFAULT_PORT = 587
DEFAULT_FROM_ADDRESS = "no-reply@localhost"
DEFAULT_FROM_NAME = "HSE Doc Studio"
DEFAULT_TIMEOUT_S = 10.0


@dataclass(frozen=True)
class SmtpParams:
    """Параметры подключения; пароль открытым текстом живёт только в памяти процесса."""

    host: str
    port: int = DEFAULT_PORT
    security: SmtpSecurity = "starttls"
    username: str | None = None
    password: str | None = None
    from_address: str = DEFAULT_FROM_ADDRESS
    from_name: str = DEFAULT_FROM_NAME
    timeout_s: float = DEFAULT_TIMEOUT_S


@dataclass(frozen=True)
class SmtpConfig:
    """Настройки для показа: пароль не входит, о нём известно только «задан или нет»."""

    host: str | None = None
    port: int = DEFAULT_PORT
    security: SmtpSecurity = "starttls"
    username: str | None = None
    password_set: bool = False
    from_address: str = DEFAULT_FROM_ADDRESS
    from_name: str = DEFAULT_FROM_NAME

    @property
    def enabled(self) -> bool:
        return bool(self.host)


@dataclass(frozen=True)
class SmtpEnv:
    """SMTP из окружения (HSE_STUDIO__MAIL__*). Заданный host запирает всю группу: половина настроек
    из окружения и половина из базы дали бы соединение, которого никто не настраивал."""

    params: SmtpParams | None = None

    @property
    def locked(self) -> bool:
        return self.params is not None

    def locked_keys(self) -> frozenset[str]:
        return frozenset(SMTP_KEYS) if self.params is not None else frozenset()


def smtp_config_from(values: Mapping[str, object]) -> SmtpConfig:
    """Непонятное значение заменяется умолчанием, а не пропускается в соединение."""
    host = values.get(KEY_HOST)
    port = values.get(KEY_PORT)
    security = values.get(KEY_SECURITY)
    username = values.get(KEY_USERNAME)
    from_address = values.get(KEY_FROM_ADDRESS)
    from_name = values.get(KEY_FROM_NAME)
    return SmtpConfig(
        host=host if isinstance(host, str) and host else None,
        port=port if isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535 else DEFAULT_PORT,
        security=security if security in SMTP_SECURITIES else "starttls",
        username=username if isinstance(username, str) and username else None,
        password_set=KEY_PASSWORD in values,
        from_address=from_address if isinstance(from_address, str) and from_address else DEFAULT_FROM_ADDRESS,
        from_name=from_name if isinstance(from_name, str) and from_name else DEFAULT_FROM_NAME,
    )


def smtp_config_of(params: SmtpParams) -> SmtpConfig:
    return SmtpConfig(
        host=params.host,
        port=params.port,
        security=params.security,
        username=params.username,
        password_set=bool(params.password),
        from_address=params.from_address,
        from_name=params.from_name,
    )
