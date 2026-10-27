"""Ключи шифрования секретов и настройки входа."""

from pathlib import Path

from pydantic import BaseModel, Field, SecretStr


class SecretsConfig(BaseModel):
    """Ключ шифрования токенов и ключей доступа (HSE_STUDIO__SECRETS__*).

    Без настроек ключ создаётся файлом в data_dir (только local). Любой из параметров выключает запись файла:
    ключ можно хранить вне тома с данными (docker secrets). В server ключ из окружения обязателен.
    """

    key: SecretStr | None = Field(
        default=None, description="Fernet key (urlsafe base64 of 32 bytes) taken from the environment."
    )
    key_file: Path | None = Field(default=None, description="File holding the Fernet key (docker secret).")
    retired_keys: SecretStr | None = Field(
        default=None,
        description="Retired Fernet keys, comma separated: they only decrypt, which makes key rotation possible.",
    )


class AuthConfig(BaseModel):
    """Вход, сессии и мастер первого запуска сервера (HSE_STUDIO__AUTH__*). Поля добавляет срез identity."""

    trusted_proxies: list[str] = Field(
        default_factory=list,
        description="IP и CIDR обратных прокси, чьему X-Forwarded-For верим при определении адреса клиента.",
    )

    session_idle_days: int = Field(
        default=7, ge=1, description="Сессия гаснет без активности столько дней (скользящий срок)."
    )
    session_absolute_days: int = Field(
        default=30, ge=1, description="Предельный возраст сессии, после которого нужен новый вход."
    )
