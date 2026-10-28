"""Ключи шифрования секретов и настройки входа."""

from pathlib import Path

from pydantic import BaseModel, Field, SecretStr

from hse_doc_studio.core.identity.entities import RegistrationMode


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

    public_url: str | None = Field(
        default=None,
        description=(
            "Внешний адрес Студии (https://studio.example.org). По схеме выбирается Secure у cookie и HSTS, "
            "адрес входит в список допустимых Origin для небезопасных запросов."
        ),
    )
    frame_ancestors: list[str] = Field(
        default_factory=list,
        description="Дополнительные источники, которым разрешено встраивать страницы Студии (frame-ancestors).",
    )
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

    registration_mode: RegistrationMode | None = Field(
        default=None,
        description=(
            "Режим регистрации из окружения: open, domains, invite или closed. "
            "Заданное побеждает БД и не правится в админке."
        ),
    )
    registration_domains: list[str] | None = Field(
        default=None,
        description="Разрешённые домены почты для режима domains; заданный список блокирует правку в админке.",
    )
    require_approval: bool | None = Field(
        default=None, description="Новые аккаунты ждут одобрения админа; заданное значение блокирует правку в админке."
    )
    password_enabled: bool | None = Field(
        default=None, description="Вход по паролю; заданное значение блокирует правку в админке."
    )

    admin_email: str | None = Field(
        default=None,
        description=(
            "Первый администратор из окружения: вместе с паролем создаётся при старте, если админа ещё нет "
            "(идемпотентно, пароль существующего не трогается). Рекомендуемый путь для compose и helm."
        ),
    )
    admin_name: str | None = Field(default=None, description="Имя первого администратора из окружения.")
    admin_password: SecretStr | None = Field(default=None, description="Пароль первого администратора из окружения.")
    admin_password_file: Path | None = Field(
        default=None, description="Файл с паролем первого администратора (docker secret)."
    )
    setup_token_required: bool | None = Field(
        default=None,
        description=(
            "Нужен ли токен установки в мастере первого запуска (печатается в журнале api). "
            "Не задано: нужен, если сервер слушает не только loopback."
        ),
    )
    experimental: bool = Field(
        default=False,
        description=(
            "Пустить server до финального среза этапа 2, минуя реестр готовности (dev-стенд server-lite). "
            "Запрещено при публичном bind: адрес сервера должен быть loopback."
        ),
    )
    experimental_in_container: bool = Field(
        default=False,
        description=(
            "Подтверждение для experimental: api слушает 0.0.0.0 внутри контейнера, а порт опубликован "
            "только на loopback хоста (compose server-lite)."
        ),
    )
