"""Актор запроса: кто обращается к API."""

from __future__ import annotations

from fastapi import HTTPException, Request

from hse_doc_studio.api.auth_cookie import credentials_from_request
from hse_doc_studio.api.config import settings
from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.identity.entities import TokenScope
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.mode import StudioMode


async def resolve_actor(request: Request) -> Actor:
    """Локальная установка одна, у неё один актор и контейнер не нужен. На сервере актора даёт цепочка
    резолверов, аноним получает 401 `auth_required`."""
    if settings.mode is StudioMode.local:
        return Actor.local()
    container = getattr(request.state, "dishka_container", None) or request.app.state.dishka_container
    resolver = await container.get(IActorResolver)
    actor = await resolver.resolve(credentials_from_request(request))
    if actor is None:
        raise IdentityError(IdentityErrorCode.auth_required)
    if actor.source is ActorSource.pat and TokenScope.api.value not in actor.scopes:
        # Токен только для git не открывает API.
        raise IdentityError(IdentityErrorCode.forbidden)
    return actor


def require_server_mode() -> None:
    """Вход, выход и сессии существуют только на сервере: у локальной установки один актор и нет cookie."""
    if settings.mode is StudioMode.local:
        raise HTTPException(status_code=404, detail="Not Found")
