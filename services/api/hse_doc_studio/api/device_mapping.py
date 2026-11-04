"""Вид устройств из ядра в контракт `/api/v1` и `/git/-/*`."""

from __future__ import annotations

from hse_doc_studio.api.schemas.builds import BuildOut, DocumentBuildsOut, ProjectBuildsResponse, StudioBuildOut
from hse_doc_studio.api.schemas.devices import (
    AccountDevicesResponse,
    AiOut,
    DeviceOut,
    DevicesOverviewResponse,
    EndpointOut,
    PdfOut,
    ProjectStudiosResponse,
    ProjectSyncOut,
    RunnerOut,
    WorkingLocallyOut,
)
from hse_doc_studio.core.devices.views import AccountDevices, DeviceView, ProjectStudios, WorkingLocally
from hse_doc_studio.use_cases.artifacts.builds import BuildInfo, ProjectBuilds, StudioBuildInfo
from hse_doc_studio.use_cases.devices.service import DevicesOverview


def map_device(view: DeviceView) -> DeviceOut:
    runner = view.runner
    project = view.project
    return DeviceOut(
        id=view.id,
        name=view.name,
        version=view.version,
        os=view.os.value,
        presence=view.presence.value,
        last_seen_at=view.last_seen_at,
        activity=view.activity.value,
        projects_count=view.projects_count,
        runner=None
        if runner is None
        else RunnerOut(
            id=runner.id,
            name=runner.name,
            state=runner.state,
            tags=list(runner.tags),
            concurrency=runner.concurrency,
            running_jobs=runner.running_jobs,
            busy=runner.busy,
        ),
        ai=AiOut(
            state=view.ai.state.value,
            endpoints=[
                EndpointOut(
                    name=e.name,
                    flavor=e.flavor,
                    reachable=e.reachable,
                    models=list(e.models),
                    provider_id=str(e.provider_id) if e.provider_id else None,
                    provider_name=e.provider_name,
                    state=e.state.value,
                )
                for e in view.ai.endpoints
            ],
        ),
        project=None
        if project is None
        else ProjectSyncOut(
            sync=project.sync.value,
            ahead=project.ahead,
            behind=project.behind,
            last_sync_at=project.last_sync_at,
            auto_sync=project.auto_sync,
            pdf=None
            if project.pdf is None
            else PdfOut(doc_id=project.pdf.doc_id, at=project.pdf.at, ok=project.pdf.ok, code=project.pdf.code),
        ),
    )


def map_people(people: tuple[WorkingLocally, ...]) -> list[WorkingLocallyOut]:
    return [WorkingLocallyOut(user_id=p.user_id, name=p.name) for p in people]


def map_project_studios(found: ProjectStudios) -> ProjectStudiosResponse:
    return ProjectStudiosResponse(
        online_window_s=found.online_window_s,
        mine=[map_device(d) for d in found.mine],
        others=map_people(found.others),
    )


def map_account_devices(found: AccountDevices) -> AccountDevicesResponse:
    return AccountDevicesResponse(online_window_s=found.online_window_s, items=[map_device(d) for d in found.items])


def map_overview(found: DevicesOverview) -> DevicesOverviewResponse:
    return DevicesOverviewResponse(
        online_window_s=found.online_window_s,
        device=map_device(found.device) if found.device is not None else None,
        others=map_people(found.others),
    )


def _build(info: BuildInfo) -> BuildOut:
    return BuildOut(
        at=info.at,
        commit=info.commit,
        pages=info.pages,
        fresh=info.fresh,
        sha256=info.sha256,
        size=info.size,
        compile_id=str(info.compile_id) if info.compile_id else None,
    )


def _studio_build(info: StudioBuildInfo) -> StudioBuildOut:
    return StudioBuildOut(**_build(info.build).model_dump(), artifact_id=str(info.artifact_id), by_name=info.by_name)


def map_builds(found: ProjectBuilds, max_pdf_bytes: int) -> ProjectBuildsResponse:
    return ProjectBuildsResponse(
        head=found.head,
        dirty=found.dirty,
        max_pdf_bytes=max_pdf_bytes,
        documents=[
            DocumentBuildsOut(
                doc_id=d.doc_id,
                cloud=None if d.cloud is None else _build(d.cloud),
                cloud_running=d.cloud_running,
                cloud_failed_at=d.cloud_failed_at,
                studio=None if d.studio is None else _studio_build(d.studio),
            )
            for d in found.documents
        ],
    )
