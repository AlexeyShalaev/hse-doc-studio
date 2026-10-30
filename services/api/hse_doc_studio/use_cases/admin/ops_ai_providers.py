"""Общие ИИ-провайдеры установки: их настраивает админ, пользователи видят их без ключа.

Общий провайдер это запись `ai_providers` с владельцем `instance`, ключ лежит шифртекстом.
Ключ наружу не отдаётся никогда, только признак `key_set`. Личные провайдеры пользователей сюда не попадают.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.ai import IAIModelLister
from hse_doc_studio.core.egress import IEgressPolicy
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderOwnerKind, AIProviderType
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.repositories import IAIProviderRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.ai_providers.base_url import authorize_base_url

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


def _instance_provider(provider: AIProvider) -> InstanceAiProvider:
    return InstanceAiProvider(
        id=provider.id,
        name=provider.name,
        type=provider.type,
        base_url=provider.base_url,
        models=tuple(provider.models),
        ssl_verify=provider.ssl_verify,
        connect_timeout_s=provider.connect_timeout_s,
        request_timeout_s=provider.request_timeout_s,
        created_at=provider.created_at,
        key_set=bool(provider.api_key),
    )


class InstanceAiProviderStore:
    """Общие провайдеры установки поверх того же хранилища, что и личные: записи с владельцем `instance`.

    Пользователи видят их в своём списке без ключа, ключ отдаёт только репозиторий админу установки.
    """

    def __init__(self, repo: IAIProviderRepository) -> None:
        self._repo = repo

    async def _shared(self, provider_id: UUID) -> AIProvider | None:
        found = await self._repo.get(provider_id)
        return found if found is not None and found.owner_kind is AIProviderOwnerKind.instance else None

    async def list(self) -> list[InstanceAiProvider]:
        found = [p for p in await self._repo.list_all() if p.owner_kind is AIProviderOwnerKind.instance]
        return [_instance_provider(p) for p in sorted(found, key=lambda p: (p.created_at, str(p.id)))]

    async def get(self, provider_id: UUID) -> InstanceAiProvider | None:
        found = await self._shared(provider_id)
        return None if found is None else _instance_provider(found)

    async def save(self, provider: InstanceAiProvider, *, api_key: str | None = None, clear_key: bool = False) -> None:
        existing = await self._shared(provider.id)
        entity = AIProvider(
            id=provider.id,
            name=provider.name,
            type=provider.type,
            api_key=api_key or "",
            base_url=provider.base_url,
            models=list(provider.models),
            created_at=provider.created_at,
            ssl_verify=provider.ssl_verify,
            connect_timeout_s=provider.connect_timeout_s,
            request_timeout_s=provider.request_timeout_s,
            owner_kind=AIProviderOwnerKind.instance,
        )
        if existing is None:
            await self._repo.create(entity)
        elif clear_key:
            # Пустой ключ при обновлении «оставить как есть», поэтому стирание идёт пересозданием записи.
            await self._repo.delete(provider.id)
            await self._repo.create(entity)
        else:
            await self._repo.update(entity)

    async def delete(self, provider_id: UUID) -> None:
        await self._repo.delete(provider_id)

    async def reveal_key(self, provider_id: UUID) -> str:
        found = await self._shared(provider_id)
        return "" if found is None else found.api_key


async def validate_base_url(base_url: str, egress: IEgressPolicy | None) -> str:
    """Адрес админа: http(s) без логина, метаданные облака и link-local закрыты всегда, частная сеть допустима."""
    value = base_url.strip()
    if not value:
        return ""
    parts = urlsplit(value)
    if parts.username or parts.password:
        raise _invalid("Адрес провайдера задан неверно.", "The provider address is not valid.")
    try:
        await authorize_base_url(egress, value, AIProviderOwnerKind.instance)
    except ValueError as exc:
        raise IdentityError(IdentityErrorCode.input_invalid, str(exc)) from exc
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
