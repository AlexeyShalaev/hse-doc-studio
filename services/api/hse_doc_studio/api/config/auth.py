"""Ключи шифрования секретов и настройки входа."""

from pathlib import Path

from pydantic import BaseModel, Field, SecretStr


class SecretsConfig(BaseModel):
    """Ключ шифрования токенов и ключей доступа (HSE_STUDIO__SECRETS__*).

    Без настроек ключ создаётся файлом в data_dir. Любой из параметров выключает запись файла:
    ключ можно хранить вне тома с данными (docker secrets).
    """

    key: SecretStr | None = Field(
        default=None, description="Fernet key (urlsafe base64 of 32 bytes) taken from the environment."
    )
    key_file: Path | None = Field(default=None, description="File holding the Fernet key (docker secret).")


class AuthConfig(BaseModel):
    """Вход, сессии и мастер первого запуска сервера (HSE_STUDIO__AUTH__*). Поля добавляет срез identity."""

    trusted_proxies: list[str] = Field(
        default_factory=list,
        description="IP и CIDR обратных прокси, чьему X-Forwarded-For верим при определении адреса клиента.",
    )
