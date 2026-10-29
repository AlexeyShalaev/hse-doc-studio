"""Провайдеры единого входа (OIDC) в админке. Секрет клиента принимается и шифруется, наружу не отдаётся."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from urllib.parse import urlsplit

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.git_sync.protocols import ISecretCipher
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.entities import OidcProvider
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog, IOidcProviderRepository
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.secrets import column_aad
from hse_doc_studio.use_cases.admin.settings import ensure_login_method_remains
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.identity.auth_settings import AuthSettingsService

_TABLE = "oidc_providers"
_COLUMN = "client_secret_enc"  # noqa: S105 — имя колонки, не секрет
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_MAX_LABEL = 128
_MAX_CLIENT_ID = 256
_MAX_SCOPES = 256


def _invalid(ru: str, en: str) -> IdentityError:
    return IdentityError(IdentityErrorCode.input_invalid, localized_error(ru, en))


def _valid_issuer(issuer: str) -> str:
    """Издатель OIDC: https (http только для локального стенда), без логина, запроса и фрагмента."""
    value = issuer.strip()
    parts = urlsplit(value)
    secure = parts.scheme == "https" or (parts.scheme == "http" and (parts.hostname or "") in _LOCAL_HOSTS)
    if not secure or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise _invalid(
            "Издатель должен быть адресом https без логина, параметров и якоря.",
            "The issuer must be an https address without credentials, query or fragment.",
        )
    return value


def _valid_scopes(scopes: str) -> str:
    items = scopes.split()
    if "openid" not in items or len(" ".join(items)) > _MAX_SCOPES:
        raise _invalid("Области доступа должны включать openid.", "The scopes must include openid.")
    return " ".join(dict.fromkeys(items))


def _valid_text(value: str, limit: int, ru: str, en: str) -> str:
    value = value.strip()
    if not value or len(value) > limit:
        raise _invalid(ru, en)
    return value


@dataclass(frozen=True)
class OidcProviderInput:
    label: str
    issuer: str
    client_id: str
    client_secret: str
    scopes: str = "openid email profile"
    enabled: bool = True
    auto_provision: bool = False


@dataclass(frozen=True)
class OidcProviderPatch:
    """Меняется только заданное (не None). Пустой `client_secret` не затирает секрет: его заменяет только новый."""

    label: str | None = None
    issuer: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    scopes: str | None = None
    enabled: bool | None = None
    auto_provision: bool | None = None


class ListOidcProvidersUC:
    def __init__(self, repo: IOidcProviderRepository) -> None:
        self._repo = repo

    async def execute(self, actor: Actor) -> list[OidcProvider]:
        require_admin(actor)
        return await self._repo.list()


class GetOidcProviderUC:
    def __init__(self, repo: IOidcProviderRepository) -> None:
        self._repo = repo

    async def execute(self, actor: Actor, provider_id: str) -> OidcProvider:
        require_admin(actor)
        provider = await self._repo.get(provider_id)
        if provider is None:
            raise IdentityError(IdentityErrorCode.not_found)
        return provider


class CreateOidcProviderUC:
    def __init__(
        self, repo: IOidcProviderRepository, cipher: ISecretCipher, audit: IAuditLog, clock: Clock = utc_now
    ) -> None:
        self._repo = repo
        self._cipher = cipher
        self._audit = audit
        self._clock = clock

    async def execute(self, actor: Actor, data: OidcProviderInput) -> OidcProvider:
        admin_id = require_admin(actor)
        provider_id = uuid.uuid4().hex
        secret = _valid_text(data.client_secret, 1024, "Укажите секрет клиента.", "Enter the client secret.")
        provider = OidcProvider(
            id=provider_id,
            label=_valid_text(data.label, _MAX_LABEL, "Укажите название.", "Enter a name."),
            issuer=_valid_issuer(data.issuer),
            client_id=_valid_text(
                data.client_id, _MAX_CLIENT_ID, "Укажите идентификатор клиента.", "Enter the client ID."
            ),
            client_secret_enc=self._cipher.encrypt(Secret(secret), aad=column_aad(_TABLE, _COLUMN, provider_id)),
            created_at=self._clock(),
            scopes=_valid_scopes(data.scopes),
            enabled=data.enabled,
            auto_provision=data.auto_provision,
        )
        await self._repo.save(provider)
        await self._audit.record(
            "oidc.create",
            actor_id=admin_id,
            target=provider_id,
            details={"label": provider.label, "issuer": provider.issuer},
        )
        return provider


class UpdateOidcProviderUC:
    def __init__(
        self,
        repo: IOidcProviderRepository,
        cipher: ISecretCipher,
        settings: AuthSettingsService,
        audit: IAuditLog,
    ) -> None:
        self._repo = repo
        self._cipher = cipher
        self._settings = settings
        self._audit = audit

    async def execute(self, actor: Actor, provider_id: str, patch: OidcProviderPatch) -> OidcProvider:
        admin_id = require_admin(actor)
        current = await self._repo.get(provider_id)
        if current is None:
            raise IdentityError(IdentityErrorCode.not_found)
        updated = replace(
            current,
            label=_valid_text(patch.label, _MAX_LABEL, "Укажите название.", "Enter a name.")
            if patch.label is not None
            else current.label,
            issuer=_valid_issuer(patch.issuer) if patch.issuer is not None else current.issuer,
            client_id=_valid_text(
                patch.client_id, _MAX_CLIENT_ID, "Укажите идентификатор клиента.", "Enter the client ID."
            )
            if patch.client_id is not None
            else current.client_id,
            scopes=_valid_scopes(patch.scopes) if patch.scopes is not None else current.scopes,
            enabled=patch.enabled if patch.enabled is not None else current.enabled,
            auto_provision=patch.auto_provision if patch.auto_provision is not None else current.auto_provision,
        )
        secret_changed = bool(patch.client_secret and patch.client_secret.strip())
        if secret_changed:
            assert patch.client_secret is not None  # noqa: S101 — проверено строкой выше
            updated = replace(
                updated,
                client_secret_enc=self._cipher.encrypt(
                    Secret(patch.client_secret.strip()), aad=column_aad(_TABLE, _COLUMN, provider_id)
                ),
            )
        if current.enabled and not updated.enabled:
            others = [p for p in await self._repo.list(only_enabled=True) if p.id != provider_id]
            await ensure_login_method_remains(self._settings, others)
        await self._repo.save(updated)
        await self._audit.record(
            "oidc.update",
            actor_id=admin_id,
            target=provider_id,
            details={"enabled": updated.enabled, "credential_changed": secret_changed},
        )
        return updated


class DeleteOidcProviderUC:
    def __init__(self, repo: IOidcProviderRepository, settings: AuthSettingsService, audit: IAuditLog) -> None:
        self._repo = repo
        self._settings = settings
        self._audit = audit

    async def execute(self, actor: Actor, provider_id: str) -> None:
        admin_id = require_admin(actor)
        current = await self._repo.get(provider_id)
        if current is None:
            raise IdentityError(IdentityErrorCode.not_found)
        if current.enabled:
            others = [p for p in await self._repo.list(only_enabled=True) if p.id != provider_id]
            await ensure_login_method_remains(self._settings, others)
        await self._repo.delete(provider_id)
        await self._audit.record("oidc.delete", actor_id=admin_id, target=provider_id, details={"label": current.label})
