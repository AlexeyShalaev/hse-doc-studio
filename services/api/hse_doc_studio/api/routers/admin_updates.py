"""`/api/admin/updates`: состояние, политика и окно, история, «обновить сейчас» и «откатить»."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from hse_doc_studio.api.config import settings
from hse_doc_studio.api.schemas.admin import PageParams, page_params
from hse_doc_studio.api.schemas.server_update import (
    ReleaseOut,
    RollbackBody,
    RunEventOut,
    RunOut,
    RunPageOut,
    StartUpdateBody,
    UpdateSettingsBody,
    UpdateStatusOut,
)
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.server_update.entities import (
    MaxBump,
    ReleaseInfo,
    UpdatePolicy,
    UpdateRun,
    UpdateSettings,
    Verify,
)
from hse_doc_studio.core.server_update.status import UpdateStatus
from hse_doc_studio.use_cases.server_update.admin import UpdateAdmin

router = APIRouter(prefix="/updates")

_NO_STORE = {"Cache-Control": "no-store"}


def _release(r: ReleaseInfo) -> ReleaseOut:
    return ReleaseOut(version=r.version, date=r.date, notes=list(r.notes), has_digest=bool(r.digests_url))


def _run(r: UpdateRun) -> RunOut:
    return RunOut(
        id=r.id,
        kind=r.kind.value,
        trigger=r.trigger.value,
        status=r.status.value,
        phase=r.phase,
        from_version=r.from_version,
        to_version=r.to_version,
        from_revision=r.from_revision,
        to_revision=r.to_revision,
        created_at=r.created_at,
        started_at=r.started_at,
        finished_at=r.finished_at,
        duration_s=r.duration_s,
        backup_run_id=r.backup_run_id,
        restore_db=r.restore_db,
        db_restored=r.db_restored,
        error_code=r.error_code,
        error=r.error,
        events=[RunEventOut(seq=e.seq, at=e.at, phase=e.phase, level=e.level, message=e.message) for e in r.events],
    )


def _settings_out(s: UpdateSettings) -> UpdateSettingsBody:
    return UpdateSettingsBody(
        policy=s.policy.value,
        channel="stable",
        max_bump=s.max_bump.value,
        window_days=list(s.window_days),
        window_start_min=s.window_start_min,
        window_minutes=s.window_minutes,
        backup_first=s.backup_first,
        verify=s.verify.value,
        notify_admins=s.notify_admins,
    )


def manual_command(executor_kind: str, version: str | None) -> str:
    """Подсказка для установок, где обновление ставит человек: compose без апдейтера или helm."""
    if executor_kind == "compose":
        return "docker compose pull && docker compose up -d"
    tag = f" --set image.tag={version}" if version else ""
    return f"helm upgrade hse-doc-studio deploy/helm/hse-doc-studio --reuse-values{tag} --atomic --wait"


def _status(st: UpdateStatus) -> UpdateStatusOut:
    return UpdateStatusOut(
        settings=_settings_out(st.settings),
        current_version=st.current_version,
        executor="compose" if st.executor_enabled else "none",
        updater_online=st.updater_online,
        updater_seen_at=st.updater_seen_at,
        updater_version=st.updater_version,
        available=_release(st.available) if st.available else None,
        auto_target=_release(st.auto_target) if st.auto_target else None,
        releases=[_release(r) for r in st.releases],
        checked_at=st.checked_at,
        check_error=st.check_error,
        in_window=st.in_window,
        next_window_at=st.next_window_at,
        backup_destination_configured=st.backup_destination_configured,
        active_run=_run(st.active_run) if st.active_run else None,
        last_run=_run(st.last_run) if st.last_run else None,
        rollback_version=st.rollback_version,
        rollback_needs_restore=st.rollback_needs_restore,
        manual_command=manual_command(settings.server_update.executor, st.available.version if st.available else None),
    )


@router.get("/status", response_model=UpdateStatusOut)
async def get_status(request: Request, response: Response) -> UpdateStatusOut:
    response.headers.update(_NO_STORE)
    uc = await request.state.dishka_container.get(UpdateAdmin)
    return _status(await uc.status(require_actor()))


@router.put("/settings", response_model=UpdateStatusOut)
async def put_settings(body: UpdateSettingsBody, request: Request, response: Response) -> UpdateStatusOut:
    response.headers.update(_NO_STORE)
    uc = await request.state.dishka_container.get(UpdateAdmin)
    new = UpdateSettings(
        policy=UpdatePolicy(body.policy),
        channel=body.channel,
        max_bump=MaxBump(body.max_bump),
        window_days=tuple(sorted(set(body.window_days))),
        window_start_min=body.window_start_min,
        window_minutes=body.window_minutes,
        backup_first=body.backup_first,
        verify=Verify(body.verify),
        notify_admins=body.notify_admins,
    )
    return _status(await uc.save_settings(require_actor(), new))


@router.post("/check", response_model=UpdateStatusOut)
async def check(request: Request, response: Response) -> UpdateStatusOut:
    response.headers.update(_NO_STORE)
    uc = await request.state.dishka_container.get(UpdateAdmin)
    return _status(await uc.check(require_actor()))


@router.post("/runs", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED)
async def start_run(body: StartUpdateBody, request: Request, response: Response) -> RunOut:
    response.headers.update(_NO_STORE)
    uc = await request.state.dishka_container.get(UpdateAdmin)
    return _run(await uc.start(require_actor(), body.version))


@router.post("/rollback", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED)
async def rollback(body: RollbackBody, request: Request, response: Response) -> RunOut:
    response.headers.update(_NO_STORE)
    uc = await request.state.dishka_container.get(UpdateAdmin)
    return _run(await uc.rollback(require_actor(), restore_db=body.restore_db))


@router.post("/runs/{run_id}/cancel", response_model=RunOut)
async def cancel_run(run_id: str, request: Request, response: Response) -> RunOut:
    response.headers.update(_NO_STORE)
    uc = await request.state.dishka_container.get(UpdateAdmin)
    return _run(await uc.cancel(require_actor(), run_id))


@router.get("/runs", response_model=RunPageOut)
async def list_runs(
    request: Request, response: Response, params: Annotated[PageParams, Depends(page_params)]
) -> RunPageOut:
    response.headers.update(_NO_STORE)
    uc = await request.state.dishka_container.get(UpdateAdmin)
    found = await uc.runs(require_actor(), params.window)
    return RunPageOut(items=[_run(r) for r in found.items], total=found.total, limit=params.limit, offset=params.offset)


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run(run_id: str, request: Request, response: Response) -> RunOut:
    response.headers.update(_NO_STORE)
    uc = await request.state.dishka_container.get(UpdateAdmin)
    return _run(await uc.run(require_actor(), run_id))
