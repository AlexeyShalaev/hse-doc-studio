"""Подключённые Студии: свои устройства человека и «Студии» проекта (только сервер, docs/design/connected-devices.md).

Человек видит свои устройства целиком. Для чужих участников проекта ответ несёт только строку «работает локально».
Отдельного маршрута для администратора установки нет: он видит то же, что обычный человек.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, Depends, HTTPException, Path, Response, status

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.device_mapping import map_account_devices, map_builds, map_project_studios
from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.schemas.builds import ProjectBuildsResponse
from hse_doc_studio.api.schemas.devices import AccountDevicesResponse, ProjectStudiosResponse
from hse_doc_studio.api.schemas.people import PresenceSignalRequest, ProjectPeopleResponse, map_people_online
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.artifacts.entities import ArtifactError
from hse_doc_studio.core.devices.entities import DEVICE_ID_RE
from hse_doc_studio.core.devices.people import SESSION_ID_RE
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.use_cases.artifacts.builds import ProjectBuildsUC
from hse_doc_studio.use_cases.devices.people import LeaveWebPresenceUC, RecordWebPresenceUC
from hse_doc_studio.use_cases.devices.service import ForgetDeviceUC, ListAccountDevicesUC, ProjectStudiosUC

router = APIRouter(route_class=SafeDishkaRoute, dependencies=[Depends(require_server_mode)])

_NO_STORE = {"Cache-Control": "no-store"}


def _person() -> Actor:
    """Вошедший человек по сессии или токену; гость по ссылке своих устройств не имеет."""
    actor = current_actor()
    if actor is None or not actor.id:
        raise IdentityError(IdentityErrorCode.auth_required)
    if actor.source not in (ActorSource.session, ActorSource.pat):
        raise IdentityError(IdentityErrorCode.forbidden)
    return actor


@router.get("/account/devices", response_model=AccountDevicesResponse)
async def list_account_devices(response: Response, uc: FromDishka[ListAccountDevicesUC]) -> AccountDevicesResponse:
    response.headers.update(_NO_STORE)
    return map_account_devices(await uc.execute(_person()))


@router.delete("/account/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def forget_account_device(
    device_id: Annotated[str, Path(max_length=32)], uc: FromDishka[ForgetDeviceUC]
) -> Response:
    if not DEVICE_ID_RE.fullmatch(device_id) or not await uc.execute(_person(), device_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/studios", response_model=ProjectStudiosResponse)
async def project_studios(
    project_id: UUID, response: Response, uc: FromDishka[ProjectStudiosUC]
) -> ProjectStudiosResponse:
    """Студии, работающие с проектом: свои целиком, чужие строкой «работает локально» (право просмотра у гарда)."""
    response.headers.update(_NO_STORE)
    actor = current_actor()
    if actor is None or actor.id is None or actor.source not in (ActorSource.session, ActorSource.pat):
        # Гость по ссылке видит проект, но не людей за ним.
        return ProjectStudiosResponse(online_window_s=0, mine=[], others=[])
    return map_project_studios(await uc.execute(actor, project_id))


@router.post("/projects/{project_id}/presence", response_model=ProjectPeopleResponse)
async def project_presence(
    project_id: UUID, body: PresenceSignalRequest, response: Response, uc: FromDishka[RecordWebPresenceUC]
) -> ProjectPeopleResponse:
    """Сигнал вкладки (раз в минуту и при смене места) и в ответ список людей, кто сейчас в проекте.

    Хранится в памяти процесса: ни записи в БД, ни строки аудита. Участнику проекта отвечает список, гостю по ссылке
    и вошедшему по ссылке пустой ответ (проект они видят, людей за ним нет).
    """
    response.headers.update(_NO_STORE)
    actor = current_actor()
    if actor is None or actor.id is None or actor.source not in (ActorSource.session, ActorSource.pat):
        return map_people_online(await uc.empty())
    return map_people_online(await uc.execute(actor, project_id, body.to_signal()))


@router.delete("/projects/{project_id}/presence/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def project_presence_leave(
    project_id: UUID, session_id: Annotated[str, Path(max_length=64)], uc: FromDishka[LeaveWebPresenceUC]
) -> Response:
    """Вкладка закрыта: её сессия уходит из списка сразу. Несуществующая сессия тоже 204: узнать чужую нельзя."""
    actor = current_actor()
    if actor is not None and SESSION_ID_RE.fullmatch(session_id):
        uc.execute(actor, project_id, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/builds", response_model=ProjectBuildsResponse)
async def project_builds(
    project_id: UUID, response: Response, uc: FromDishka[ProjectBuildsUC]
) -> ProjectBuildsResponse:
    """Где и когда собран каждый документ (облако, Студия), из какого коммита и свежий ли PDF."""
    response.headers.update(_NO_STORE)
    try:
        found = await uc.execute(project_id)
    except ArtifactError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message) from exc
    return map_builds(found, settings.artifacts.max_pdf_bytes)
