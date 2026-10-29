"""Настройки исходящей почты: чтение с учётом окружения, правка админом и тестовое письмо."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.git_sync.errors import GitSyncError
from hse_doc_studio.core.git_sync.protocols import ISecretCipher
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode, message_for
from hse_doc_studio.core.identity.normalize import is_valid_email
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository, IMailSender, IUserRepository
from hse_doc_studio.core.identity.setting_source import SettingDescription, describe_setting
from hse_doc_studio.core.identity.smtp_settings import (
    KEY_FROM_ADDRESS,
    KEY_FROM_NAME,
    KEY_HOST,
    KEY_PASSWORD,
    KEY_PORT,
    KEY_SECURITY,
    KEY_USERNAME,
    SMTP_KEYS,
    SMTP_SECURITIES,
    SmtpConfig,
    SmtpEnv,
    SmtpParams,
    SmtpSecurity,
    smtp_config_from,
    smtp_config_of,
)
from hse_doc_studio.core.secrets import column_aad
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.identity.auth_settings import SOURCE_ADMIN

_log = logging.getLogger(__name__)

SECRET_TABLE = "instance_settings"  # noqa: S105 — имя таблицы, не пароль
SECRET_COLUMN = "secret_enc"  # noqa: S105 — имя колонки, не пароль

# Что менять после правки (пересоздать почтовик под новые настройки).
ChangeHook = Callable[[], Awaitable[None]]


@dataclass(frozen=True)
class SmtpSettingsView:
    config: SmtpConfig
    descriptions: dict[str, SettingDescription]

    def describe(self, key: str) -> SettingDescription:
        return self.descriptions[key]


class SmtpSettingsService:
    def __init__(self, repo: IInstanceSettingsRepository, cipher: ISecretCipher, env: SmtpEnv | None = None) -> None:
        self._repo = repo
        self._cipher = cipher
        self._env = env or SmtpEnv()

    @property
    def locked(self) -> bool:
        return self._env.locked

    async def view(self) -> SmtpSettingsView:
        values = await self._repo.get_all()
        locked = self._env.locked_keys()
        config = smtp_config_of(self._env.params) if self._env.params is not None else smtp_config_from(values)
        stored = set(values)
        return SmtpSettingsView(config, {key: describe_setting(key, stored=stored, locked=locked) for key in SMTP_KEYS})

    async def params(self) -> SmtpParams | None:
        """Параметры для соединения либо None, если почта выключена."""
        if self._env.params is not None:
            return self._env.params
        values = await self._repo.get_all()
        config = smtp_config_from(values)
        if config.host is None:
            return None
        return SmtpParams(
            host=config.host,
            port=config.port,
            security=config.security,
            username=config.username,
            password=await self._password(),
            from_address=config.from_address,
            from_name=config.from_name,
        )

    async def _password(self) -> str | None:
        token = await self._repo.get_secret(KEY_PASSWORD)
        if token is None:
            return None
        try:
            return self._cipher.decrypt(token, aad=column_aad(SECRET_TABLE, SECRET_COLUMN, KEY_PASSWORD)).reveal()
        except GitSyncError:
            # Не открылся ключом: письма пойдут без пароля и упадут на стороне SMTP, ссылки останутся в outbox.
            _log.warning("smtp password cannot be decrypted")
            return None

    def seal(self, password: str) -> str:
        return self._cipher.encrypt(Secret(password), aad=column_aad(SECRET_TABLE, SECRET_COLUMN, KEY_PASSWORD))


class GetSmtpSettingsUC:
    def __init__(self, service: SmtpSettingsService) -> None:
        self._service = service

    async def execute(self, actor: Actor) -> SmtpSettingsView:
        require_admin(actor)
        return await self._service.view()


@dataclass(frozen=True)
class SmtpPatch:
    """Меняется только заданное (не None). `host=""` выключает почту, `username=""` и `password=""` стирают значение."""

    host: str | None = None
    port: int | None = None
    security: SmtpSecurity | None = None
    username: str | None = None
    password: str | None = None
    from_address: str | None = None
    from_name: str | None = None


def _invalid(ru: str, en: str) -> IdentityError:
    return IdentityError(IdentityErrorCode.forbidden, localized_error(ru, en))


class UpdateSmtpSettingsUC:
    def __init__(
        self,
        service: SmtpSettingsService,
        repo: IInstanceSettingsRepository,
        audit: IAuditLog,
        on_change: ChangeHook | None = None,
    ) -> None:
        self._service = service
        self._repo = repo
        self._audit = audit
        self._on_change = on_change

    async def execute(self, actor: Actor, patch: SmtpPatch) -> SmtpSettingsView:
        """Заданное окружением не правится: отказ целиком, ничего не записывается. Пароль в журнал не попадает."""
        admin_id = require_admin(actor)
        if self._service.locked:
            raise IdentityError(
                IdentityErrorCode.setting_locked,
                f"{message_for(IdentityErrorCode.setting_locked)} ({KEY_HOST})",
            )
        changes = self._validated(patch)
        for key, value in changes.items():
            if value in (None, ""):
                await self._repo.delete(key)
            else:
                await self._repo.set(key, value, source=SOURCE_ADMIN)
        await self._store_password(patch.password)
        changed = sorted(changes) + ([KEY_PASSWORD] if patch.password is not None else [])
        if changed:
            await self._audit.record(
                "settings.smtp_update",
                actor_id=admin_id,
                details={"fields": changed, "credential_changed": patch.password is not None},
            )
            if self._on_change is not None:
                await self._on_change()
        return await self._service.view()

    async def _store_password(self, password: str | None) -> None:
        if password is None:
            return
        if password:
            await self._repo.set_secret(KEY_PASSWORD, self._service.seal(password), source=SOURCE_ADMIN)
        else:
            await self._repo.delete(KEY_PASSWORD)

    @staticmethod
    def _validated(patch: SmtpPatch) -> dict[str, object]:
        pairs: dict[str, object | None] = {
            KEY_HOST: patch.host.strip() if patch.host is not None else None,
            KEY_PORT: patch.port,
            KEY_SECURITY: patch.security,
            KEY_USERNAME: patch.username.strip() if patch.username is not None else None,
            KEY_FROM_ADDRESS: patch.from_address.strip() if patch.from_address is not None else None,
            KEY_FROM_NAME: patch.from_name.strip() if patch.from_name is not None else None,
        }
        if patch.port is not None and not 1 <= patch.port <= 65535:
            raise _invalid("Порт SMTP вне диапазона 1-65535.", "The SMTP port must be between 1 and 65535.")
        if patch.security is not None and patch.security not in SMTP_SECURITIES:
            raise _invalid("Неизвестный вид защиты соединения.", "Unknown connection security.")
        host = pairs[KEY_HOST]
        if isinstance(host, str) and (any(c.isspace() or c in "/@" for c in host) or len(host) > 253):
            raise _invalid("Адрес SMTP-сервера задан неверно.", "The SMTP server address is not valid.")
        address = pairs[KEY_FROM_ADDRESS]
        if isinstance(address, str) and address and not is_valid_email(address):
            raise _invalid("Адрес отправителя задан неверно.", "The sender address is not valid.")
        return {key: value for key, value in pairs.items() if value is not None}


@dataclass(frozen=True)
class SmtpTestResult:
    ok: bool
    error: str | None = None


class SendTestMailUC:
    def __init__(self, sender: IMailSender, users: IUserRepository, audit: IAuditLog) -> None:
        self._sender = sender
        self._users = users
        self._audit = audit

    async def execute(self, actor: Actor, to: str | None) -> SmtpTestResult:
        """Письмо уходит по сохранённым настройкам; сбой возвращается как результат, а не как ошибка запроса."""
        admin_id = require_admin(actor)
        # Актор несёт подпись коммитов, а не почту аккаунта: по умолчанию пишем на адрес самого админа из аккаунта.
        account = None if to else await self._users.get(admin_id)
        recipient = (to or (account.email if account else "")).strip()
        if not is_valid_email(recipient):
            raise _invalid("Укажите адрес получателя.", "Enter a recipient address.")
        if not self._sender.enabled:
            raise _invalid("SMTP не настроен.", "SMTP is not configured.")
        try:
            await self._sender.send(
                recipient,
                "HSE Doc Studio: проверка почты / mail check",
                "Это тестовое письмо Студии. Если вы его читаете, отправка настроена верно.\n\n"
                "This is a test message from the Studio. If you can read it, mail sending works.",
            )
        except Exception as exc:
            await self._audit.record("settings.smtp_test", actor_id=admin_id, details={"ok": False})
            return SmtpTestResult(False, f"{type(exc).__name__}: {str(exc)[:200]}")
        await self._audit.record("settings.smtp_test", actor_id=admin_id, details={"ok": True})
        return SmtpTestResult(True)
