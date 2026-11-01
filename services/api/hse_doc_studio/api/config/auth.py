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


class OidcEnvConfig(BaseModel):
    """Единственный провайдер OIDC из окружения (HSE_STUDIO__AUTH__OIDC__*). Остальные заводятся в админке.

    Провайдер включается, когда заданы issuer, client_id и секрет клиента (значением или файлом).
    """

    id: str = Field(default="sso", pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$", description="Идентификатор в адресах входа.")
    label: str = Field(default="SSO", max_length=128, description="Название на кнопке входа.")
    issuer: str | None = Field(default=None, description="Адрес издателя (discovery лежит под ним).")
    client_id: str | None = Field(default=None, description="Идентификатор клиента у провайдера.")
    client_secret: SecretStr | None = Field(default=None, description="Секрет клиента.")
    client_secret_file: Path | None = Field(default=None, description="Файл с секретом клиента (docker secret).")
    scopes: str = Field(default="openid email profile", description="Запрашиваемые области.")
    auto_provision: bool = Field(
        default=False, description="Создавать аккаунт при первом входе в обход политики регистрации."
    )

    def resolved_secret(self) -> str:
        if self.client_secret is not None and self.client_secret.get_secret_value():
            return self.client_secret.get_secret_value()
        if self.client_secret_file is not None:
            try:
                return self.client_secret_file.read_text(encoding="utf-8").strip()
            except OSError:
                return ""
        return ""

    @property
    def configured(self) -> bool:
        return bool(self.issuer and self.client_id and self.resolved_secret())


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
    project_invites_allow_signup: bool | None = Field(
        default=None,
        description=(
            "Приглашение в проект даёт право зарегистрироваться в режиме invite (по умолчанию да); "
            "заданное значение блокирует правку в админке."
        ),
    )

    oidc: OidcEnvConfig = Field(default_factory=OidcEnvConfig, description="Провайдер OIDC из окружения.")

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
            "Не задано: нужен, если сервер слушает не только loopback, задан внешний public_url или trusted_proxies."
        ),
    )
