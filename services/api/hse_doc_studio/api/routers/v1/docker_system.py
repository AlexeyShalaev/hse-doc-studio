from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException

from hse_doc_studio.api.schemas.docker_system import (
    CleanupJobResponse,
    CleanupJobStateResponse,
    CleanupStepResponse,
    DockerCleanupRequest,
    DockerContainerUsageResponse,
    DockerImageUsageResponse,
    DockerUsageResponse,
    DockerVolumeUsageResponse,
)
from hse_doc_studio.infra.docker.cleanup_jobs import CleanupJob
from hse_doc_studio.use_cases.system.cleanup_docker import (
    CancelDockerCleanupUC,
    GetDockerCleanupJobUC,
    StartDockerCleanupInput,
    StartDockerCleanupUC,
)
from hse_doc_studio.use_cases.system.get_docker_disk_usage import GetDockerDiskUsageUC

router = APIRouter(route_class=DishkaRoute)


def _map_job(job: CleanupJob | None) -> CleanupJobResponse | None:
    if job is None:
        return None
    return CleanupJobResponse(
        id=job.id,
        status=job.status,
        steps=[
            CleanupStepResponse(
                kind=step.kind,
                ref=step.ref,
                status=step.status,
                freed_bytes=step.freed_bytes,
                error=step.error,
            )
            for step in job.steps
        ],
        freed_bytes=job.freed_bytes,
    )


@router.get("/system/docker-usage", response_model=DockerUsageResponse)
async def get_docker_usage(
    uc: FromDishka[GetDockerDiskUsageUC],
) -> DockerUsageResponse:
    result = await uc.execute()
    usage = result.usage
    return DockerUsageResponse(
        available=usage.available,
        images=[
            DockerImageUsageResponse(
                reference=i.reference,
                repository=i.repository,
                tag=i.tag,
                size_bytes=i.size_bytes,
                created=i.created,
                in_use=i.containers > 0,
                category=i.category,
                dangling=i.dangling,
                protected=i.protected,
            )
            for i in usage.images
        ],
        containers=[
            DockerContainerUsageResponse(
                name=c.name,
                image=c.image,
                state=c.state,
                status=c.status,
                size_bytes=c.size_bytes,
                managed=c.managed,
            )
            for c in usage.containers
        ],
        volumes=[
            DockerVolumeUsageResponse(
                name=v.name,
                size_bytes=v.size_bytes,
                links=v.links,
                managed=v.managed,
            )
            for v in usage.volumes
        ],
        images_total_bytes=usage.images_total_bytes,
        containers_total_bytes=usage.containers_total_bytes,
        volumes_total_bytes=usage.volumes_total_bytes,
        build_cache_bytes=usage.build_cache_bytes,
        build_cache_reclaimable_bytes=usage.build_cache_reclaimable_bytes,
        build_cache_count=usage.build_cache_count,
        total_bytes=usage.total_bytes,
        cleanable_bytes=result.cleanable_bytes,
    )


@router.post("/system/docker-cleanup", status_code=202, response_model=CleanupJobResponse)
async def start_docker_cleanup(
    body: DockerCleanupRequest,
    uc: FromDishka[StartDockerCleanupUC],
) -> CleanupJobResponse:
    try:
        job = await uc.execute(
            StartDockerCleanupInput(
                targets=list(body.targets),
                images=list(body.images),
                containers=list(body.containers),
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    mapped = _map_job(job)
    assert mapped is not None  # noqa: S101 — start() always returns a job
    return mapped


@router.get("/system/docker-cleanup", response_model=CleanupJobStateResponse)
async def get_docker_cleanup(
    uc: FromDishka[GetDockerCleanupJobUC],
) -> CleanupJobStateResponse:
    return CleanupJobStateResponse(job=_map_job(await uc.execute()))


@router.post("/system/docker-cleanup/cancel", response_model=CleanupJobStateResponse)
async def cancel_docker_cleanup(
    uc: FromDishka[CancelDockerCleanupUC],
) -> CleanupJobStateResponse:
    return CleanupJobStateResponse(job=_map_job(await uc.execute()))
