from __future__ import annotations

import json
from collections.abc import AsyncIterator

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from hse_doc_studio.api.schemas.images import (
    DockerStatusResponse,
    ImagesListResponse,
    LocalImageResponse,
    RemoteTagResponse,
    RemoteTagsResponse,
    SetActiveImageRequest,
    SetActiveImageResponse,
)
from hse_doc_studio.infra.compile.docker_image_manager import (
    LocalImageInfo,
    RemoteTagInfo,
)
from hse_doc_studio.use_cases.compile.get_docker_status import GetDockerStatusUC
from hse_doc_studio.use_cases.compile.install_image import (
    InstallImageInput,
    InstallImageUC,
)
from hse_doc_studio.use_cases.compile.list_images import ListImagesUC
from hse_doc_studio.use_cases.compile.list_remote_tags import (
    ListRemoteTagsInput,
    ListRemoteTagsUC,
)
from hse_doc_studio.use_cases.compile.remove_image import (
    RemoveImageInput,
    RemoveImageUC,
)
from hse_doc_studio.use_cases.compile.set_active_image import (
    SetActiveImageInput,
    SetActiveImageUC,
)

router = APIRouter(route_class=DishkaRoute)


def _map_local(info: LocalImageInfo) -> LocalImageResponse:
    return LocalImageResponse(
        image=info.image,
        repository=info.repository,
        tag=info.tag,
        id=info.id,
        size_bytes=info.size_bytes,
        created=info.created,
    )


def _map_remote(info: RemoteTagInfo) -> RemoteTagResponse:
    return RemoteTagResponse(
        name=info.name,
        size_bytes=info.size_bytes,
        last_updated=info.last_updated,
    )


@router.get("/compile/docker-status", response_model=DockerStatusResponse)
async def get_docker_status(
    uc: FromDishka[GetDockerStatusUC],
) -> DockerStatusResponse:
    result = await uc.execute()
    return DockerStatusResponse(
        available=result.status.available,
        version=result.status.version,
        detail=result.status.detail,
        reason=str(result.status.reason) if result.status.reason else None,
        socket_gid=result.status.socket_gid,
    )


@router.get("/compile/images", response_model=ImagesListResponse)
async def list_images(
    uc: FromDishka[ListImagesUC],
) -> ImagesListResponse:
    result = await uc.execute()
    return ImagesListResponse(
        active_image=result.active_image,
        allowed_repos=result.allowed_repos,
        installed=[_map_local(i) for i in result.installed],
    )


@router.get("/compile/images/remote", response_model=RemoteTagsResponse)
async def list_remote_tags(
    repo: str,
    uc: FromDishka[ListRemoteTagsUC],
) -> RemoteTagsResponse:
    try:
        result = await uc.execute(ListRemoteTagsInput(repo=repo))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RemoteTagsResponse(
        repo=result.repo,
        tags=[_map_remote(t) for t in result.tags],
    )


@router.post("/compile/images/active", response_model=SetActiveImageResponse)
async def set_active_image(
    body: SetActiveImageRequest,
    uc: FromDishka[SetActiveImageUC],
) -> SetActiveImageResponse:
    try:
        result = await uc.execute(SetActiveImageInput(image=body.image))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SetActiveImageResponse(image=result.image)


@router.delete("/compile/images", status_code=204)
async def remove_image(
    image: str,
    uc: FromDishka[RemoveImageUC],
) -> None:
    try:
        await uc.execute(RemoveImageInput(image=image))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/compile/images/install")
async def install_image(
    image: str,
    uc: FromDishka[InstallImageUC],
) -> StreamingResponse:
    """Stream `docker pull <image>` output via SSE.

    GET (not POST) because EventSource only speaks GET. `docker pull` is
    idempotent — pulling an already-installed image is a noop — so the
    side-effect-via-GET smell doesn't bite us. The image tag goes as a
    query parameter because tags contain slashes and colons that are ugly
    to URL-encode in a path segment.
    """
    try:
        stream = await uc.execute(InstallImageInput(image=image))
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
