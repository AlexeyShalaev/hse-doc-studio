"""Image management for the managed office services (зеркало languagetool.py).

- "convert" — Gotenberg (pptx→PDF-предпросмотр, infra/office/convert_manager);
- "editor" — ONLYOFFICE Document Server (in-app редактор, editor_manager).

Формы ошибок и SSE-формат установки — строго как у LanguageTool, чтобы фронт
переиспользовал готовые типы/SSE-код LT-секции. Неизвестный {service} → 422
(Literal в path-параметре).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Literal

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from hse_doc_studio.api.schemas.office_services import (
    OfficeServiceContainerResponse,
    OfficeServiceImageResponse,
    OfficeServiceImagesListResponse,
    OfficeServiceRemoteTagResponse,
    OfficeServiceRemoteTagsResponse,
    OfficeServicesStatusResponse,
    OfficeServiceStatusResponse,
    SetActiveOfficeServiceImageRequest,
    SetActiveOfficeServiceImageResponse,
)
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.infra.compile.docker_image_manager import LocalImageInfo, RemoteTagInfo
from hse_doc_studio.use_cases.office_services.get_office_services_status import (
    GetOfficeServicesStatusUC,
)
from hse_doc_studio.use_cases.office_services.install_office_service_image import (
    InstallOfficeServiceImageInput,
    InstallOfficeServiceImageUC,
)
from hse_doc_studio.use_cases.office_services.list_office_service_images import (
    ListOfficeServiceImagesInput,
    ListOfficeServiceImagesUC,
)
from hse_doc_studio.use_cases.office_services.list_office_service_remote_tags import (
    ListOfficeServiceRemoteTagsInput,
    ListOfficeServiceRemoteTagsUC,
)
from hse_doc_studio.use_cases.office_services.set_active_office_service_image import (
    SetActiveOfficeServiceImageInput,
    SetActiveOfficeServiceImageUC,
)

router = APIRouter(route_class=DishkaRoute)

# 422 на любой сервис, кроме известных (см. контракт: convert | editor).
OfficeService = Literal["convert", "editor"]


def _map_local(info: LocalImageInfo, active_image: str) -> OfficeServiceImageResponse:
    return OfficeServiceImageResponse(
        tag=info.image,
        size=info.size_bytes,
        created=info.created,
        active=info.image == active_image,
        installed=True,
    )


def _map_remote(info: RemoteTagInfo) -> OfficeServiceRemoteTagResponse:
    return OfficeServiceRemoteTagResponse(
        name=info.name,
        size_bytes=info.size_bytes,
        last_updated=info.last_updated,
    )


@router.get("/office-services/status", response_model=OfficeServicesStatusResponse)
async def get_office_services_status(
    uc: FromDishka[GetOfficeServicesStatusUC],
) -> OfficeServicesStatusResponse:
    r = await uc.execute()
    return OfficeServicesStatusResponse(
        services=[
            OfficeServiceStatusResponse(
                service=s.service,
                label_hint=s.label_hint,
                active_image=s.active_image,
                image_installed=s.image_installed,
                container=OfficeServiceContainerResponse(
                    present=s.container.present,
                    running=s.container.running,
                    status_text=s.container.status_text,
                ),
            )
            for s in r.services
        ]
    )


@router.get("/office-services/{service}/images", response_model=OfficeServiceImagesListResponse)
async def list_office_service_images(
    service: OfficeService,
    uc: FromDishka[ListOfficeServiceImagesUC],
) -> OfficeServiceImagesListResponse:
    result = await uc.execute(ListOfficeServiceImagesInput(service=service))
    return OfficeServiceImagesListResponse(
        active_image=result.active_image,
        allowed_repos=result.allowed_repos,
        images=[_map_local(i, result.active_image) for i in result.installed],
    )


@router.get("/office-services/{service}/images/remote", response_model=OfficeServiceRemoteTagsResponse)
async def list_office_service_remote_tags(
    service: OfficeService,
    uc: FromDishka[ListOfficeServiceRemoteTagsUC],
    repo: str | None = None,
) -> OfficeServiceRemoteTagsResponse:
    try:
        result = await uc.execute(ListOfficeServiceRemoteTagsInput(service=service, repo=repo))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return OfficeServiceRemoteTagsResponse(
        repo=result.repo,
        tags=[_map_remote(t) for t in result.tags],
    )


@router.post("/office-services/{service}/images/active", response_model=SetActiveOfficeServiceImageResponse)
async def set_active_office_service_image(
    service: OfficeService,
    body: SetActiveOfficeServiceImageRequest,
    uc: FromDishka[SetActiveOfficeServiceImageUC],
) -> SetActiveOfficeServiceImageResponse:
    try:
        result = await uc.execute(SetActiveOfficeServiceImageInput(service=service, image=body.image))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SetActiveOfficeServiceImageResponse(image=result.image)


@router.get("/office-services/{service}/images/install")
async def install_office_service_image(
    service: OfficeService,
    image: str,
    uc: FromDishka[InstallOfficeServiceImageUC],
) -> StreamingResponse:
    """Stream `docker pull <image>` output via SSE (GET, как у LT install)."""
    try:
        stream = await uc.execute(InstallOfficeServiceImageInput(service=service, image=image))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def _event_stream() -> AsyncIterator[str]:
        done_payload: dict[str, object] = {"status": "success"}
        async for line in stream:
            if line == "__DONE__":
                done_payload["status"] = "success"
                continue
            if line == "__FAILED__":
                done_payload["status"] = "failure"
                continue
            yield f"event: log\ndata: {json.dumps(line, ensure_ascii=False)}\n\n"
        yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
