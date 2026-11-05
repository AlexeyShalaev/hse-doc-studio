"""Связь локальной Студии с облаком: устройство, присутствие и сборки (только локальный режим).

Облако видит только то, что Студия сама сообщает: имя устройства, версию, коды состояний и числа. Путей на диске,
содержимого документов и ключей среди этого нет (docs/design/connected-devices.md, раздел 4).
"""

from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, Depends, HTTPException

from hse_doc_studio.api.actor import require_local_mode
from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.schemas.builds import BuildOut
from hse_doc_studio.api.schemas.devices import DevicesOverviewResponse, ProjectSyncOut
from hse_doc_studio.api.schemas.studio_link import (
    CancelCloudBuildsRequest,
    CancelCloudBuildsResponse,
    DeviceNameRequest,
    DocumentBuildStatusOut,
    FetchBuildRequest,
    FetchBuildResponse,
    FetchOutcomeOut,
    LastPresenceOut,
    LinkServerOut,
    LocalBuildOut,
    LocalBuildsResponse,
    LocalDeviceOut,
    LocalEndpointOut,
    LocalRunnerOut,
    StudioLinkResponse,
)
from hse_doc_studio.core.devices.local import IDeviceIdentity, LocalDevice
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_remote.client import StudioServerError, StudioServerErrorCode
from hse_doc_studio.core.git_remote.cloud_builds import CloudBuild
from hse_doc_studio.core.git_sync.errors import GitSyncError
from hse_doc_studio.use_cases.devices.local_builds import DocumentBuildStatus, LocalBuild, LocalBuildsUC
from hse_doc_studio.use_cases.devices.local_presence import LastPresence, LinkServer, LocalPresenceService

router = APIRouter(route_class=SafeDishkaRoute, dependencies=[Depends(require_local_mode)])


def _device(device: LocalDevice) -> LocalDeviceOut:
    return LocalDeviceOut(
        device_id=device.device_id, name=device.name, default_name=device.default_name, custom=device.custom
    )


@router.get("/device", response_model=LocalDeviceOut)
async def get_device(identity: FromDishka[IDeviceIdentity]) -> LocalDeviceOut:
    return _device(await identity.get())


@router.put("/device", response_model=LocalDeviceOut)
async def rename_device(body: DeviceNameRequest, identity: FromDishka[IDeviceIdentity]) -> LocalDeviceOut:
    """Имя, под которым облако показывает эту Студию; пустое возвращает имя машины."""
    return _device(await identity.set_name(body.name))


def _last(last: LastPresence | None) -> LastPresenceOut | None:
    if last is None:
        return None
    return LastPresenceOut(
        at=last.at, ok=last.ok, code=last.code, interval_s=last.interval_s, online_window_s=last.online_window_s
    )


def _server(item: LinkServer) -> LinkServerOut:
    return LinkServerOut(
        credential_id=str(item.credential_id),
        server_url=item.server_url,
        host=item.host,
        state=item.state,
        account_name=item.account_name,
        last=_last(item.last),
        cloud=DevicesOverviewResponse.model_validate(item.cloud) if item.cloud is not None else None,
        cloud_error=item.cloud_error,
    )


@router.get("/git/studio-link", response_model=StudioLinkResponse)
async def studio_link(uc: FromDishka[LocalPresenceService], project: UUID | None = None) -> StudioLinkResponse:
    """Связь с облаком одним ответом: вошли ли вы, видит ли облако эту Студию, раннер, модели, кто ещё онлайн."""
    found = await uc.link(project)
    return StudioLinkResponse(
        device=_device(found.device),
        runner=LocalRunnerOut(
            state=found.runner.state,
            paired=found.runner.paired,
            name=found.runner.name,
            running_jobs=found.runner.running_jobs,
            enabled=found.runner.enabled,
        ),
        endpoints=[
            LocalEndpointOut(
                name=e.name,
                flavor=e.flavor,
                announced=e.announced,
                reachable=e.reachable,
                models=list(e.models),
            )
            for e in found.endpoints
        ],
        servers=[_server(item) for item in found.servers],
        project=_project(found.project),
    )


def _project(report: dict[str, object] | None) -> ProjectSyncOut | None:
    """Состояние проекта на этой Студии: `project_id` нужен серверу, а в ответе окну он лишний."""
    if report is None:
        return None
    return ProjectSyncOut.model_validate({k: v for k, v in report.items() if k != "project_id"})


def _cloud(build: CloudBuild | None) -> BuildOut | None:
    if build is None:
        return None
    return BuildOut(
        at=build.at,
        commit=build.commit,
        pages=build.pages,
        fresh=build.fresh,
        sha256=build.sha256,
        size=build.size,
        compile_id=str(build.compile_id) if build.compile_id else None,
    )


def _local(build: LocalBuild | None) -> LocalBuildOut | None:
    if build is None:
        return None
    return LocalBuildOut(
        at=build.at,
        commit=build.commit,
        fresh=build.fresh,
        sha256=build.sha256,
        pages=build.pages,
        from_cloud=build.from_cloud,
    )


def _document(item: DocumentBuildStatus) -> DocumentBuildStatusOut:
    return DocumentBuildStatusOut(
        doc_id=item.doc_id,
        local=_local(item.local),
        cloud=_cloud(item.cloud),
        cloud_running=item.cloud_running,
        studio=_cloud(item.studio),
        relation=item.relation.value,
        can_fetch=item.can_fetch,
    )


@router.get("/projects/{project_id}/git/builds", response_model=LocalBuildsResponse)
async def local_builds(project_id: UUID, uc: FromDishka[LocalBuildsUC]) -> LocalBuildsResponse:
    """Где и когда собран каждый документ (эта Студия, облако), из какого коммита и совпадают ли сборки."""
    try:
        found = await uc.status(project_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return LocalBuildsResponse(
        connected=found.connected,
        cloud_error=found.cloud_error,
        local_head=found.local_head,
        local_dirty=found.local_dirty,
        cloud_head=found.cloud_head,
        documents=[_document(d) for d in found.documents],
    )


@router.post("/projects/{project_id}/git/builds/cancel", response_model=CancelCloudBuildsResponse)
async def cancel_cloud_builds(
    project_id: UUID, body: CancelCloudBuildsRequest, uc: FromDishka[LocalBuildsUC]
) -> CancelCloudBuildsResponse:
    """Остановить облачную сборку (в очереди или на раннере) по входу этой Студии; повтор безвреден."""
    try:
        stopped = await uc.cancel_cloud(project_id, body.doc_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StudioServerError as exc:
        status = {
            StudioServerErrorCode.unauthorized: 401,
            StudioServerErrorCode.cancel_forbidden: 403,
            StudioServerErrorCode.cancel_unsupported: 501,
        }.get(exc.code, 502)
        raise HTTPException(status_code=status, detail=exc.code) from exc
    return CancelCloudBuildsResponse(cancelled=stopped)


@router.post("/projects/{project_id}/git/builds/fetch", response_model=FetchBuildResponse)
async def fetch_cloud_builds(
    project_id: UUID, body: FetchBuildRequest, uc: FromDishka[LocalBuildsUC]
) -> FetchBuildResponse:
    """Получить готовый PDF облачной сборки: тот же отпечаток не качается, более свежую локальную сборку не затираем."""
    try:
        items = await uc.fetch(project_id, body.doc_id, force=body.force, auto=body.auto)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StudioServerError as exc:
        status = 401 if exc.code == StudioServerErrorCode.unauthorized else 502
        raise HTTPException(status_code=status, detail=exc.code) from exc
    except GitSyncError:
        raise
    return FetchBuildResponse(
        items=[FetchOutcomeOut(doc_id=i.doc_id, status=i.status.value, code=i.code, size=i.size) for i in items]
    )
