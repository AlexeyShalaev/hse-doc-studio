"""`/api/admin/runner-install`: поставить раннер на этой же машине (docker рядом или Deployment в кластере)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from hse_doc_studio.api.runner_commands import studio_base_url
from hse_doc_studio.api.schemas.runner_install import (
    CapabilityInfo,
    InstallJobInfo,
    InstallStepInfo,
    LocalCapabilitiesResponse,
    LocalInstanceInfo,
    LocalTargetName,
    StartLocalInstallRequest,
)
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.jobs.errors import RunnerNotFoundError
from hse_doc_studio.core.runner_install import Capability, InstallJob, InstallTarget, LocalInstance, UnavailableReason
from hse_doc_studio.use_cases.runner_install import InstallBusyError, InstallUnavailableError, RunnerInstallService

router = APIRouter(prefix="/runner-install")

_NO_STORE = {"Cache-Control": "no-store"}


async def _service(request: Request) -> RunnerInstallService:
    return await request.state.dishka_container.get(RunnerInstallService)


def _capability(value: Capability) -> CapabilityInfo:
    return CapabilityInfo(available=value.available, reason=value.reason.value if value.reason else None)


def job_info(job: InstallJob) -> InstallJobInfo:
    return InstallJobInfo(
        id=job.id,
        target=job.target.value,
        name=job.name,
        state=job.state.value,
        steps=[InstallStepInfo(key=s.key, state=s.state.value, detail=s.detail) for s in job.steps],
        error_code=job.error_code,
        error_detail=job.error_detail,
        created_at=job.created_at,
    )


def _instance(item: LocalInstance) -> LocalInstanceInfo:
    return LocalInstanceInfo(
        target=item.target.value,
        name=item.name,
        image=item.image,
        state=item.state,
        created_at=item.created_at,
    )


@router.get("/local", response_model=LocalCapabilitiesResponse)
async def local_capabilities(request: Request, response: Response) -> LocalCapabilitiesResponse:
    """Где здесь можно поставить раннер; причина недоступности объясняет, почему кнопки нет."""
    response.headers.update(_NO_STORE)
    found = await (await _service(request)).capabilities(require_actor())
    no_host = Capability.no(UnavailableReason.disabled)
    return LocalCapabilitiesResponse(
        docker=_capability(found.get(InstallTarget.docker, no_host)),
        kubernetes=_capability(found.get(InstallTarget.kubernetes, no_host)),
    )


@router.get("/local/instances", response_model=list[LocalInstanceInfo])
async def local_instances(request: Request, response: Response) -> list[LocalInstanceInfo]:
    response.headers.update(_NO_STORE)
    return [_instance(i) for i in await (await _service(request)).instances(require_actor())]


@router.post("/local/{target}", response_model=InstallJobInfo, status_code=status.HTTP_202_ACCEPTED)
async def start_local_install(
    target: LocalTargetName, body: StartLocalInstallRequest, request: Request, response: Response
) -> InstallJobInfo:
    response.headers.update(_NO_STORE)
    try:
        job = await (await _service(request)).start(
            require_actor(),
            InstallTarget(target),
            studio_url=studio_base_url(request),
            name=body.name or None,
            concurrency=body.concurrency,
        )
    except InstallUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "install_unavailable", "reason": exc.reason}
        ) from exc
    except InstallBusyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "install_busy"}) from exc
    return job_info(job)


@router.delete("/local/{target}/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_local_instance(target: LocalTargetName, name: str, request: Request) -> Response:
    try:
        await (await _service(request)).remove(require_actor(), InstallTarget(target), name)
    except RunnerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/jobs/{job_id}", response_model=InstallJobInfo)
async def install_job(job_id: str, request: Request, response: Response) -> InstallJobInfo:
    response.headers.update(_NO_STORE)
    job = (await _service(request)).job(require_actor(), job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    return job_info(job)
