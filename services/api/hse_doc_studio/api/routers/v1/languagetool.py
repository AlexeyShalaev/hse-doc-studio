from __future__ import annotations

import json
from collections.abc import AsyncIterator

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from hse_doc_studio.api.schemas.languagetool import (
    LanguageToolImageResponse,
    LanguageToolImagesListResponse,
    LanguageToolRemoteTagResponse,
    LanguageToolRemoteTagsResponse,
    LanguageToolStatusResponse,
    SetActiveLanguageToolImageRequest,
    SetActiveLanguageToolImageResponse,
)
from hse_doc_studio.infra.compile.docker_image_manager import LocalImageInfo, RemoteTagInfo
from hse_doc_studio.use_cases.languagetool.get_languagetool_status import GetLanguageToolStatusUC
from hse_doc_studio.use_cases.languagetool.install_languagetool_image import (
    InstallLanguageToolImageInput,
    InstallLanguageToolImageUC,
)
from hse_doc_studio.use_cases.languagetool.list_languagetool_images import ListLanguageToolImagesUC
from hse_doc_studio.use_cases.languagetool.list_languagetool_remote_tags import (
    ListLanguageToolRemoteTagsInput,
    ListLanguageToolRemoteTagsUC,
)
from hse_doc_studio.use_cases.languagetool.remove_languagetool_image import (
    RemoveLanguageToolImageInput,
    RemoveLanguageToolImageUC,
)
from hse_doc_studio.use_cases.languagetool.set_active_languagetool_image import (
    SetActiveLanguageToolImageInput,
    SetActiveLanguageToolImageUC,
)

router = APIRouter(route_class=DishkaRoute)


def _map_local(info: LocalImageInfo) -> LanguageToolImageResponse:
    return LanguageToolImageResponse(
        image=info.image,
        repository=info.repository,
        tag=info.tag,
        id=info.id,
        size_bytes=info.size_bytes,
        created=info.created,
    )


def _map_remote(info: RemoteTagInfo) -> LanguageToolRemoteTagResponse:
    return LanguageToolRemoteTagResponse(
        name=info.name,
        size_bytes=info.size_bytes,
        last_updated=info.last_updated,
    )


@router.get("/languagetool/status", response_model=LanguageToolStatusResponse)
async def get_languagetool_status(
    uc: FromDishka[GetLanguageToolStatusUC],
) -> LanguageToolStatusResponse:
    r = await uc.execute()
    return LanguageToolStatusResponse(
        docker_available=r.docker_available,
        docker_detail=r.docker_detail,
        docker_reason=r.docker_reason,
        docker_socket_gid=r.docker_socket_gid,
        active_image=r.active_image,
        image_installed=r.image_installed,
        container_present=r.container_present,
        container_running=r.container_running,
        container_status=r.container_status,
        healthy=r.healthy,
        base_url=r.base_url,
    )


@router.get("/languagetool/images", response_model=LanguageToolImagesListResponse)
async def list_languagetool_images(
    uc: FromDishka[ListLanguageToolImagesUC],
) -> LanguageToolImagesListResponse:
    result = await uc.execute()
    return LanguageToolImagesListResponse(
        active_image=result.active_image,
        allowed_repos=result.allowed_repos,
        installed=[_map_local(i) for i in result.installed],
    )


@router.get("/languagetool/images/remote", response_model=LanguageToolRemoteTagsResponse)
async def list_languagetool_remote_tags(
    repo: str,
    uc: FromDishka[ListLanguageToolRemoteTagsUC],
) -> LanguageToolRemoteTagsResponse:
    try:
        result = await uc.execute(ListLanguageToolRemoteTagsInput(repo=repo))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LanguageToolRemoteTagsResponse(
        repo=result.repo,
        tags=[_map_remote(t) for t in result.tags],
    )


@router.post("/languagetool/images/active", response_model=SetActiveLanguageToolImageResponse)
async def set_active_languagetool_image(
    body: SetActiveLanguageToolImageRequest,
    uc: FromDishka[SetActiveLanguageToolImageUC],
) -> SetActiveLanguageToolImageResponse:
    try:
        result = await uc.execute(SetActiveLanguageToolImageInput(image=body.image))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SetActiveLanguageToolImageResponse(image=result.image)


@router.delete("/languagetool/images", status_code=204)
async def remove_languagetool_image(
    image: str,
    uc: FromDishka[RemoveLanguageToolImageUC],
) -> None:
    try:
        await uc.execute(RemoveLanguageToolImageInput(image=image))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/languagetool/images/install")
async def install_languagetool_image(
    image: str,
    uc: FromDishka[InstallLanguageToolImageUC],
) -> StreamingResponse:
    """Stream `docker pull <image>` output via SSE (GET, like the compile install)."""
    try:
        stream = await uc.execute(InstallLanguageToolImageInput(image=image))
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
