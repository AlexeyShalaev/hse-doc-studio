"""Сокет совместной правки (`/api/collab/v1/projects/{id}/room?path=`): протокол y-websocket поверх комнаты файла.

Вне `/api/v1`: гард маршрутов рассчитан на HTTP-запрос, поэтому сокет сам проверяет Origin (браузер не защищает
сокеты от чужих страниц), разбирает актора и право на файл. Код закрытия говорит клиенту, что делать: 4401
войти заново, 4403 нет права, 4404 нет файла, 4415 файл не текст, 4429 занято (лимиты), 1013 клиент отстал.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import replace
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from hse_doc_studio.api.auth_cookie import credentials_from_request
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.guards import linked_actor
from hse_doc_studio.core.access.checker import ProjectForbiddenError
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.identity.entities import TokenScope
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.collab import protocol as proto
from hse_doc_studio.infra.collab.manager import (
    CLOSE_FORBIDDEN,
    CLOSE_NOT_FOUND,
    Client,
    CollabIdentity,
    CollabManager,
    CollabRefusedError,
    Room,
)
from hse_doc_studio.use_cases.collab.access import AuthorizeCollabUC, CollabAccess

_log = logging.getLogger(__name__)
CLOSE_UNAUTHENTICATED = 4401
_MAX_PATH = 512

router = APIRouter()


class _Socket:
    """Адаптер WebSocket под порт комнаты."""

    def __init__(self, ws: WebSocket) -> None:
        self._ws = ws

    async def send_bytes(self, data: bytes) -> None:
        await self._ws.send_bytes(data)

    async def close(self, code: int, reason: str) -> None:
        if self._ws.application_state is WebSocketState.CONNECTED:
            with contextlib.suppress(RuntimeError, WebSocketDisconnect):
                await self._ws.close(code=code, reason=reason)


def _origin_allowed(ws: WebSocket) -> bool:
    origin = ws.headers.get("origin")
    if origin is None:
        return True
    parts = urlsplit(origin.strip().lower())
    normalized = f"{parts.scheme}://{parts.netloc}"
    allowed = {o.lower().rstrip("/") for o in settings.cors.allow_origins if o and o != "*"}
    public = settings.auth.public_url
    if public:
        public_parts = urlsplit(public.strip().lower())
        allowed.add(f"{public_parts.scheme}://{public_parts.netloc}")
    host = ws.headers.get("host", "").lower()
    return normalized in allowed or (bool(host) and normalized in (f"http://{host}", f"https://{host}"))


async def _actor(ws: WebSocket, project_id: UUID) -> Actor:
    container = ws.app.state.dishka_container
    resolver = await container.get(IActorResolver)
    actor = await resolver.resolve(credentials_from_request(ws))
    if actor is None:
        raise IdentityError(IdentityErrorCode.auth_required)
    if actor.source is ActorSource.pat and TokenScope.api.value not in actor.scopes:
        raise ProjectForbiddenError("Forbidden")
    set_current_actor(actor)
    # Лениво: локальная сборка живёт без extra server, а sqlalchemy тянет репозиторий членства.
    from hse_doc_studio.infra.db.repositories.project_acl import PostgresProjectAclRepository  # noqa: PLC0415

    acl = await (await container.get(PostgresProjectAclRepository)).load_for(actor, project_id)
    grant = acl.grant_for(actor) if acl is not None else None
    if grant is not None and grant.via_link:
        actor = await linked_actor(ws, actor, grant.link_id)
        set_current_actor(actor)
    return actor


async def _pump(ws: WebSocket, client: Client) -> None:
    """Пишет кадры из очереди клиента в сокет; пустой кадр значит «комната закрыта»."""
    try:
        while True:
            frame = await client.outbox.get()
            if not frame:
                return
            await ws.send_bytes(frame)
    except (WebSocketDisconnect, RuntimeError):
        return


async def _recheck(
    ws: WebSocket, project_id: UUID, path: str, client: Client, authorize: AuthorizeCollabUC, every: float
) -> None:
    """Пересматривает право во время сессии: отзыв закрывает сокет, смена роли переключает запись и чтение."""
    while True:
        await asyncio.sleep(every)
        try:
            access = await authorize.execute(project_id, path)
        except (ProjectForbiddenError, NotFoundError, IdentityError):
            await ws.close(code=CLOSE_FORBIDDEN, reason="revoked")
            return
        if access.can_write != client.identity.can_write:
            client.identity = replace(client.identity, can_write=access.can_write)
            client.send(proto.event_frame({"type": "role", "can_write": access.can_write}))


def _identity(access: CollabAccess) -> CollabIdentity:
    return CollabIdentity(key=access.key, name=access.name, can_write=access.can_write)


@router.websocket("/api/collab/v1/projects/{project_id}/room")
async def room_socket(ws: WebSocket, project_id: UUID, path: str = Query(min_length=1, max_length=_MAX_PATH)) -> None:
    if settings.mode is StudioMode.local or not _origin_allowed(ws):
        await ws.close(code=1008)
        return
    await ws.accept()
    container = ws.app.state.dishka_container
    try:
        actor = await _actor(ws, project_id)
        authorize = await container.get(AuthorizeCollabUC)
        manager = await container.get(CollabManager)
        access = await authorize.execute(project_id, path.lstrip("/"))
        room, client = await manager.join(project_id, path.lstrip("/"), _Socket(ws), _identity(access))
    except IdentityError:
        await ws.close(code=CLOSE_UNAUTHENTICATED, reason="auth_required")
        return
    except ProjectForbiddenError:
        await ws.close(code=CLOSE_FORBIDDEN, reason="forbidden")
        return
    except NotFoundError:
        await ws.close(code=CLOSE_NOT_FOUND, reason="not_found")
        return
    except CollabRefusedError as refused:
        await ws.close(code=refused.code, reason=refused.reason)
        return
    del actor
    await _serve(ws, manager, room, client, authorize, project_id, path.lstrip("/"))


async def _serve(
    ws: WebSocket,
    manager: CollabManager,
    room: Room,
    client: Client,
    authorize: AuthorizeCollabUC,
    project_id: UUID,
    path: str,
) -> None:
    pump = asyncio.create_task(_pump(ws, client))
    recheck = asyncio.create_task(_recheck(ws, project_id, path, client, authorize, manager.config.recheck_s))
    limit = manager.config.max_message_bytes
    try:
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                break
            data = message.get("bytes")
            if data is None:
                continue
            if len(data) > limit:
                await ws.close(code=1009, reason="too_large")
                break
            await room.receive(client, data)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        for task in (pump, recheck):
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await asyncio.gather(pump, recheck, return_exceptions=True)
        manager.leave(room, client)
