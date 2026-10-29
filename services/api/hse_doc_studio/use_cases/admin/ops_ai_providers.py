"""Общие ИИ-провайдеры установки: их настраивает админ, пользователи видят их без ключа.

Запись провайдера лежит в `instance_settings` под `ai_provider/<id>`, ключ отдельной зашифрованной
строкой `ai_provider_key/<id>`. Ключ наружу не отдаётся никогда, только признак `key_set`.
Личные провайдеры пользователей живут отдельно и сюда не попадают.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.ai import IAIModelLister
from hse_doc_studio.core.egress import EgressBlockedError, EgressPurpose, IEgressPolicy
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderType
from hse_doc_studio.core.git_sync.errors import GitSyncError
from hse_doc_studio.core.git_sync.protocols import ISecretCipher
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository
from hse_doc_studio.core.secrets import column_aad
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.identity.auth_settings import SOURCE_ADMIN

_log = logging.getLogger(__name__)

META_PREFIX = "ai_provider/"
KEY_PREFIX = "ai_provider_key/"
SECRET_TABLE = "instance_settings"  # noqa: S105 — имя таблицы, не пароль
SECRET_COLUMN = "secret_enc"  # noqa: S105 — имя колонки, не пароль
MAX_NAME = 128
MAX_MODELS = 200
MAX_MODEL_LEN = 200


@dataclass(frozen=True)
class InstanceAiProvider:
    id: UUID
    name: str
    type: AIProviderType
    base_url: str
    models: tuple[str, ...]
    ssl_verify: bool
    connect_timeout_s: float
    request_timeout_s: float
    created_at: datetime
    key_set: bool


@dataclass(frozen=True)
class InstanceAiProviderInput:
    name: str
    type: AIProviderType
    api_key: str = ""
    base_url: str = ""
    models: tuple[str, ...] = ()
    ssl_verify: bool = True
    connect_timeout_s: float = 10.0
    request_timeout_s: float = 60.0


@dataclass(frozen=True)
class InstanceAiProviderPatch:
    """Меняется только заданное (не None). Пустой `api_key` оставляет прежний, стирает только `clear_key`."""

    name: str | None = None
    type: AIProviderType | None = None
    api_key: str | None = None
    clear_key: bool = False
    base_url: str | None = None
    models: tuple[str, ...] | None = None
    ssl_verify: bool | None = None
    connect_timeout_s: float | None = None
    request_timeout_s: float | None = None


@dataclass(frozen=True)
class ProviderCheck:
    ok: bool
    models: tuple[str, ...] = ()
    error: str | None = None


def _invalid(ru: str, en: str) -> IdentityError:
    return IdentityError(IdentityErrorCode.input_invalid, localized_error(ru, en))


def _not_found() -> IdentityError:
    return IdentityError(IdentityErrorCode.not_found)


def _meta(provider: InstanceAiProvider) -> dict[str, Any]:
    return {
        "name": provider.name,
        "type": provider.type.value,
        "base_url": provider.base_url,
        "models": list(provider.models),
        "ssl_verify": provider.ssl_verify,
        "connect_timeout_s": provider.connect_timeout_s,
        "request_timeout_s": provider.request_timeout_s,
        "created_at": provider.created_at.isoformat(),
    }


def _provider_of(provider_id: str, raw: object, values: Mapping[str, object]) -> InstanceAiProvider | None:
    if not isinstance(raw, dict):
        return None
    try:
        return InstanceAiProvider(
            id=UUID(provider_id),
            name=str(raw["name"]),
            type=AIProviderType(raw["type"]),
            base_url=str(raw.get("base_url", "")),
            models=tuple(str(m) for m in raw.get("models", [])),
            ssl_verify=bool(raw.get("ssl_verify", True)),
            connect_timeout_s=float(raw.get("connect_timeout_s", 10.0)),
            request_timeout_s=float(raw.get("request_timeout_s", 60.0)),
            created_at=datetime.fromisoformat(str(raw["created_at"])),
            key_set=f"{KEY_PREFIX}{provider_id}" in values,
        )
    except (KeyError, ValueError, TypeError):
        return None


class InstanceAiProviderStore:
    """Чтение и запись общих провайдеров поверх настроек установки."""

    def __init__(self, repo: IInstanceSettingsRepository, cipher: ISecretCipher) -> None:
        self._repo = repo
        self._cipher = cipher

    async def list(self) -> list[InstanceAiProvider]:
        values = await self._repo.get_all()
        found = (
            _provider_of(key.removeprefix(META_PREFIX), raw, values)
            for key, raw in values.items()
            if key.startswith(META_PREFIX)
        )
        return sorted((p for p in found if p is not None), key=lambda p: (p.created_at, str(p.id)))

    async def get(self, provider_id: UUID) -> InstanceAiProvider | None:
        values = await self._repo.get_all()
        return _provider_of(str(provider_id), values.get(f"{META_PREFIX}{provider_id}"), values)

    async def save(self, provider: InstanceAiProvider, *, api_key: str | None = None, clear_key: bool = False) -> None:
        await self._repo.set(f"{META_PREFIX}{provider.id}", _meta(provider), source=SOURCE_ADMIN)
        key_name = f"{KEY_PREFIX}{provider.id}"
        if clear_key:
            await self._repo.delete(key_name)
        elif api_key:
            token = self._cipher.encrypt(Secret(api_key), aad=column_aad(SECRET_TABLE, SECRET_COLUMN, key_name))
            await self._repo.set_secret(key_name, token, source=SOURCE_ADMIN)

    async def delete(self, provider_id: UUID) -> None:
        await self._repo.delete(f"{META_PREFIX}{provider_id}")
        await self._repo.delete(f"{KEY_PREFIX}{provider_id}")

    async def reveal_key(self, provider_id: UUID) -> str:
        key_name = f"{KEY_PREFIX}{provider_id}"
        token = await self._repo.get_secret(key_name)
        if token is None:
            return ""
        try:
            return self._cipher.decrypt(token, aad=column_aad(SECRET_TABLE, SECRET_COLUMN, key_name)).reveal()
        except GitSyncError:
            _log.warning("instance ai provider key cannot be decrypted")
            return ""


async def validate_base_url(base_url: str, egress: IEgressPolicy | None) -> str:
    """Адрес админа: http(s) без логина, метаданные облака и link-local закрыты всегда, частная сеть допустима."""
    value = base_url.strip()
    if not value:
        return ""
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise _invalid("Адрес провайдера задан неверно.", "The provider address is not valid.")
    if egress is not None:
        try:
            await egress.authorize(parts.hostname, parts.port, purpose=EgressPurpose.admin)
        except EgressBlockedError as exc:
            raise _invalid(
                "Этот адрес закрыт для запросов сервера.", "This address is blocked for server requests."
            ) from exc
        except OSError:
            raise _invalid("Адрес провайдера не разрешается.", "The provider address does not resolve.") from None
    return value


def _checked_models(models: tuple[str, ...]) -> tuple[str, ...]:
    cleaned = tuple(dict.fromkeys(m.strip() for m in models if m.strip()))
    if len(cleaned) > MAX_MODELS or any(len(m) > MAX_MODEL_LEN for m in cleaned):
        raise _invalid("Слишком длинный список моделей.", "The model list is too long.")
    return cleaned


def _checked_name(name: str) -> str:
    value = name.strip()
    if not value or len(value) > MAX_NAME:
        raise _invalid("Укажите название провайдера.", "Provider name is required.")
    return value


def _checked_timeouts(connect_s: float, request_s: float) -> None:
    if not 0 < connect_s <= 300 or not 0 < request_s <= 600:
        raise _invalid("Таймауты вне допустимого.", "Timeouts are out of range.")


class ListInstanceAiProvidersUC:
    def __init__(self, store: InstanceAiProviderStore) -> None:
        self._store = store

    async def execute(self, actor: Actor) -> list[InstanceAiProvider]:
        require_admin(actor)
        return await self._store.list()


class GetInstanceAiProviderUC:
    def __init__(self, store: InstanceAiProviderStore) -> None:
        self._store = store

    async def execute(self, actor: Actor, provider_id: UUID) -> InstanceAiProvider:
        require_admin(actor)
        provider = await self._store.get(provider_id)
        if provider is None:
            raise _not_found()
        return provider


class CreateInstanceAiProviderUC:
    def __init__(
        self, store: InstanceAiProviderStore, audit: IAuditLog, uow: IUnitOfWork, egress: IEgressPolicy | None = None
    ) -> None:
        self._store = store
        self._audit = audit
        self._uow = uow
        self._egress = egress

    async def execute(self, actor: Actor, data: InstanceAiProviderInput) -> InstanceAiProvider:
        admin_id = require_admin(actor)
        name = _checked_name(data.name)
        _checked_timeouts(data.connect_timeout_s, data.request_timeout_s)
        if data.type is not AIProviderType.ollama and not data.api_key.strip():
            raise _invalid("Укажите API-ключ.", "An API key is required.")
        provider = InstanceAiProvider(
            id=uuid4(),
            name=name,
            type=data.type,
            base_url=await validate_base_url(data.base_url, self._egress),
            models=_checked_models(data.models),
            ssl_verify=data.ssl_verify,
            connect_timeout_s=data.connect_timeout_s,
            request_timeout_s=data.request_timeout_s,
            created_at=datetime.now(UTC),
            key_set=bool(data.api_key.strip()),
        )
        async with self._uow.begin():
            await self._store.save(provider, api_key=data.api_key.strip())
            await self._audit.record(
                "settings.ai_provider_create",
                actor_id=admin_id,
                target=str(provider.id),
                details={"name": provider.name, "type": provider.type.value},
            )
        return provider


class UpdateInstanceAiProviderUC:
    def __init__(
        self, store: InstanceAiProviderStore, audit: IAuditLog, uow: IUnitOfWork, egress: IEgressPolicy | None = None
    ) -> None:
        self._store = store
        self._audit = audit
        self._uow = uow
        self._egress = egress

    async def execute(self, actor: Actor, provider_id: UUID, patch: InstanceAiProviderPatch) -> InstanceAiProvider:
        admin_id = require_admin(actor)
        current = await self._store.get(provider_id)
        if current is None:
            raise _not_found()
        key = (patch.api_key or "").strip()
        updated = replace(
            current,
            name=_checked_name(patch.name) if patch.name is not None else current.name,
            type=patch.type if patch.type is not None else current.type,
            base_url=(
                await validate_base_url(patch.base_url, self._egress)
                if patch.base_url is not None
                else current.base_url
            ),
            models=_checked_models(patch.models) if patch.models is not None else current.models,
            ssl_verify=patch.ssl_verify if patch.ssl_verify is not None else current.ssl_verify,
            connect_timeout_s=(
                patch.connect_timeout_s if patch.connect_timeout_s is not None else current.connect_timeout_s
            ),
            request_timeout_s=(
                patch.request_timeout_s if patch.request_timeout_s is not None else current.request_timeout_s
            ),
            key_set=(current.key_set or bool(key)) and not patch.clear_key,
        )
        _checked_timeouts(updated.connect_timeout_s, updated.request_timeout_s)
        async with self._uow.begin():
            await self._store.save(updated, api_key=key, clear_key=patch.clear_key)
            await self._audit.record(
                "settings.ai_provider_update",
                actor_id=admin_id,
                target=str(provider_id),
                details={"credential_changed": bool(key) or patch.clear_key},
            )
        return updated


class DeleteInstanceAiProviderUC:
    def __init__(self, store: InstanceAiProviderStore, audit: IAuditLog, uow: IUnitOfWork) -> None:
        self._store = store
        self._audit = audit
        self._uow = uow

    async def execute(self, actor: Actor, provider_id: UUID) -> None:
        admin_id = require_admin(actor)
        current = await self._store.get(provider_id)
        if current is None:
            raise _not_found()
        async with self._uow.begin():
            await self._store.delete(provider_id)
            await self._audit.record(
                "settings.ai_provider_delete",
                actor_id=admin_id,
                target=str(provider_id),
                details={"name": current.name},
            )


class CheckInstanceAiProviderUC:
    """Живая проверка: список моделей у провайдера. Сбой провайдера это ответ `ok=false`, а не ошибка запроса."""

    def __init__(self, store: InstanceAiProviderStore, lister: IAIModelLister) -> None:
        self._store = store
        self._lister = lister

    async def execute(self, actor: Actor, provider_id: UUID) -> ProviderCheck:
        require_admin(actor)
        current = await self._store.get(provider_id)
        if current is None:
            raise _not_found()
        entity = AIProvider(
            id=current.id,
            name=current.name,
            type=current.type,
            api_key=await self._store.reveal_key(provider_id),
            base_url=current.base_url,
            models=list(current.models),
            created_at=current.created_at,
            ssl_verify=current.ssl_verify,
            connect_timeout_s=current.connect_timeout_s,
            request_timeout_s=current.request_timeout_s,
        )
        try:
            models = await self._lister.list_models(entity)
        except Exception as exc:
            return ProviderCheck(ok=False, error=type(exc).__name__)
        return ProviderCheck(ok=True, models=tuple(models))
