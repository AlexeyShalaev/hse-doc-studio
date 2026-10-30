"""ИИ-провайдеры в Postgres: личные виден и меняет только владелец, общие провайдеры установки видны всем без ключа."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import ColumnElement, and_, delete, func, or_, select, update

from hse_doc_studio.core.access.context import ActorRequired, require_actor
from hse_doc_studio.core.access.entities import Actor, ActorKind
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderOwnerKind, AIProviderType
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.errors import GitSyncError
from hse_doc_studio.core.git_sync.protocols import ISecretCipher
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode, message_for
from hse_doc_studio.core.listing import Paged
from hse_doc_studio.core.repositories import InstanceAiProviderQuery
from hse_doc_studio.core.secrets import column_aad
from hse_doc_studio.infra.db.orm.ai_providers import AIProviderRow
from hse_doc_studio.infra.db.search import matches_any, ordered
from hse_doc_studio.infra.db.session import SessionProvider

logger = structlog.get_logger()

_USER = AIProviderOwnerKind.user.value
_INSTANCE = AIProviderOwnerKind.instance.value


class PostgresAIProviderRepository:
    """IAIProviderRepository сервера.

    Личного провайдера видят и меняют только его владелец; чужой неотличим от несуществующего. Общий провайдер
    установки видят все, но ключ получает только админ установки, остальным вместо него пустая строка; менять и
    удалять общий может только админ. Ключ лежит шифртекстом, привязанным к таблице, колонке и id записи. Пустой
    ключ при обновлении столбец не затирает: «оставить как есть» решает use case, а нечитаемый ключ не
    потеряется при сохранении остальных полей.
    """

    def __init__(self, sessions: SessionProvider, cipher: ISecretCipher) -> None:
        self._sessions = sessions
        self._cipher = cipher

    async def list_all(self) -> list[AIProvider]:
        actor = _actor()
        stmt = select(AIProviderRow).where(_visible(actor)).order_by(AIProviderRow.created_at, AIProviderRow.id)
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [self._to_entity(row, actor, strict=False) for row in rows]

    async def list_instance(self, query: InstanceAiProviderQuery) -> Paged[AIProvider]:
        """Общие провайдеры установки страницей; ключ расшифровывается только у строк страницы и только админу."""
        actor = _actor()
        conditions: list[ColumnElement[bool]] = [AIProviderRow.owner_kind == _INSTANCE]
        if query.q:
            conditions.append(matches_any(query.q, [AIProviderRow.name, AIProviderRow.base_url]))
        if query.types:
            conditions.append(AIProviderRow.type.in_(sorted(t.value for t in query.types)))
        keys: dict[str, list[Any]] = {
            "name": [func.lower(AIProviderRow.name)],
            "type": [AIProviderRow.type],
            "created_at": [AIProviderRow.created_at],
        }
        stmt = (
            select(AIProviderRow)
            .where(*conditions)
            .order_by(*ordered(query.sort, keys, AIProviderRow.id))
            .limit(query.window.limit)
            .offset(query.window.offset)
        )
        async with self._sessions.use() as session:
            total = (
                await session.execute(select(func.count()).select_from(AIProviderRow).where(*conditions))
            ).scalar_one()
            rows = (await session.execute(stmt)).scalars().all()
        return Paged(items=tuple(self._to_entity(row, actor, strict=False) for row in rows), total=int(total))

    async def get(self, provider_id: UUID) -> AIProvider | None:
        actor = _actor()
        async with self._sessions.use() as session:
            row = (
                await session.execute(select(AIProviderRow).where(AIProviderRow.id == provider_id, _visible(actor)))
            ).scalar_one_or_none()
        return None if row is None else self._to_entity(row, actor, strict=True)

    async def create(self, provider: AIProvider) -> None:
        actor = _actor()
        shared = provider.owner_kind is AIProviderOwnerKind.instance
        if shared and not actor.is_instance_admin:
            raise _forbidden()
        async with self._sessions.use() as session:
            session.add(
                AIProviderRow(
                    id=provider.id,
                    owner_kind=provider.owner_kind.value,
                    owner_id=None if shared else actor.id,
                    name=provider.name,
                    type=str(provider.type),
                    api_key_enc=self._seal(provider.id, provider.api_key),
                    base_url=provider.base_url,
                    models=list(provider.models),
                    ssl_verify=provider.ssl_verify,
                    connect_timeout_s=provider.connect_timeout_s,
                    request_timeout_s=provider.request_timeout_s,
                    created_at=provider.created_at,
                )
            )

    async def update(self, provider: AIProvider) -> None:
        actor = _actor()
        values: dict[str, object] = {
            "name": provider.name,
            "type": str(provider.type),
            "base_url": provider.base_url,
            "models": list(provider.models),
            "ssl_verify": provider.ssl_verify,
            "connect_timeout_s": provider.connect_timeout_s,
            "request_timeout_s": provider.request_timeout_s,
        }
        if provider.api_key:
            values["api_key_enc"] = self._seal(provider.id, provider.api_key)
        async with self._sessions.use() as session:
            result = await session.execute(
                update(AIProviderRow)
                .where(AIProviderRow.id == provider.id, _writable(actor))
                .values(**values)
                .returning(AIProviderRow.id)
            )
            if result.first() is None:
                raise NotFoundError(
                    localized_error(f"AI-провайдер {provider.id} не найден", f"AI provider {provider.id} not found")
                )

    async def delete(self, provider_id: UUID) -> bool:
        actor = _actor()
        async with self._sessions.use() as session:
            result = await session.execute(
                delete(AIProviderRow)
                .where(AIProviderRow.id == provider_id, _writable(actor))
                .returning(AIProviderRow.id)
            )
            return result.first() is not None

    def _seal(self, provider_id: UUID, api_key: str) -> str | None:
        if not api_key:
            return None
        return self._cipher.encrypt(Secret(api_key), aad=column_aad("ai_providers", "api_key_enc", provider_id))

    def _open(self, row: AIProviderRow, actor: Actor, *, strict: bool) -> str:
        """Общий ключ нужен только админу. Нечитаемый ключ в списке не роняет весь список, а в get сообщает причину."""
        if row.api_key_enc is None or (row.owner_kind == _INSTANCE and not actor.is_instance_admin):
            return ""
        try:
            return self._cipher.decrypt(row.api_key_enc, aad=column_aad("ai_providers", "api_key_enc", row.id)).reveal()
        except GitSyncError:
            if strict:
                raise
            logger.warning("ai provider key cannot be decrypted", provider_id=str(row.id))
            return ""

    def _to_entity(self, row: AIProviderRow, actor: Actor, *, strict: bool) -> AIProvider:
        return AIProvider(
            id=row.id,
            name=row.name,
            type=AIProviderType(row.type),
            api_key=self._open(row, actor, strict=strict),
            base_url=row.base_url,
            models=[str(model) for model in row.models],
            created_at=row.created_at,
            ssl_verify=row.ssl_verify,
            connect_timeout_s=row.connect_timeout_s,
            request_timeout_s=row.request_timeout_s,
            owner_kind=AIProviderOwnerKind(row.owner_kind),
        )


def _actor() -> Actor:
    actor = require_actor()
    if actor.kind is not ActorKind.user or actor.id is None:
        raise ActorRequired("провайдеры ИИ доступны только пользователю")
    return actor


def _forbidden() -> IdentityError:
    return IdentityError(IdentityErrorCode.forbidden, message_for(IdentityErrorCode.forbidden))


def _own(actor: Actor) -> ColumnElement[bool]:
    return and_(AIProviderRow.owner_kind == _USER, AIProviderRow.owner_id == actor.id)


def _visible(actor: Actor) -> ColumnElement[bool]:
    return or_(_own(actor), AIProviderRow.owner_kind == _INSTANCE)


def _writable(actor: Actor) -> ColumnElement[bool]:
    return or_(_own(actor), AIProviderRow.owner_kind == _INSTANCE) if actor.is_instance_admin else _own(actor)
