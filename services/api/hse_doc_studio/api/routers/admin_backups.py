"""`/api/admin/backups`: назначения, расписание и хранение, запуск, история, бэкапы в хранилище.

Восстановления здесь нет намеренно: оно заменяет базу, из которой живёт сам api (docs/design/backups.md, раздел 5).
Админка показывает готовую команду CLI.
"""

from __future__ import annotations

import shlex
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from hse_doc_studio.api.config import settings
from hse_doc_studio.api.schemas.admin import PageParams, page_params
from hse_doc_studio.api.schemas.backups import (
    CheckDestinationBody,
    CheckResultInfo,
    DestinationBody,
    DestinationInfo,
    RunInfo,
    RunPage,
    SettingsBody,
    SettingsInfo,
    StartRunBody,
    StatusInfo,
    StoredBackupInfo,
    StoredBackupPart,
)
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.backup.entities import (
    BackupDestination,
    BackupRun,
    BackupSettings,
    DestinationKind,
    DestinationSpec,
    EncryptionMode,
    StoredBackup,
)
from hse_doc_studio.core.backup.schedule import Schedule, ScheduleKind
from hse_doc_studio.use_cases.backup.destinations import (
    CheckResult,
    CreateDestinationUC,
    DeleteDestinationUC,
    DestinationInput,
    ListDestinationsUC,
    TestDestinationUC,
    UpdateDestinationUC,
)
from hse_doc_studio.use_cases.backup.runs import (
    DeleteStoredBackupUC,
    GetRunUC,
    ListRunsUC,
    ListStoredBackupsUC,
    StartBackupUC,
)
from hse_doc_studio.use_cases.backup.settings import BackupStatus, GetBackupSettingsUC, UpdateBackupSettingsUC

router = APIRouter(prefix="/backups")

_NO_STORE = {"Cache-Control": "no-store"}


def _destination(d: BackupDestination) -> DestinationInfo:
    return DestinationInfo(
        id=d.id,
        name=d.spec.name,
        kind=d.spec.kind.value,
        is_default=d.is_default,
        endpoint=d.spec.endpoint,
        region=d.spec.region,
        bucket=d.spec.bucket,
        prefix=d.spec.prefix,
        path_style=d.spec.path_style,
        local_path=d.spec.local_path,
        access_key_hint=d.access_key_hint,
        secret_key_set=d.secret_key_set,
        created_at=d.created_at,
        updated_at=d.updated_at,
        last_check_at=d.last_check_at,
        last_check_ok=d.last_check_ok,
        last_check_error=d.last_check_error,
    )


def _run(r: BackupRun) -> RunInfo:
    return RunInfo(
        id=r.id,
        destination_id=r.destination_id,
        destination_name=r.destination_name,
        trigger=r.trigger.value,
        status=r.status.value,
        stage=r.stage,
        started_at=r.started_at,
        finished_at=r.finished_at,
        duration_s=r.duration_s,
        size_bytes=r.size_bytes,
        backup_id=r.backup_id,
        error=r.error,
        removed_at=r.removed_at,
    )


def _settings(s: BackupSettings, *, passphrase_set: bool) -> SettingsInfo:
    return SettingsInfo(
        enabled=s.enabled,
        schedule_kind=s.schedule.kind.value,
        interval_hours=s.schedule.interval_hours,
        cron=s.schedule.cron,
        keep_last=s.keep_last,
        keep_days=s.keep_days,
        encryption_mode=s.encryption_mode.value,
        notify_admins=s.notify_admins,
        passphrase_set=passphrase_set,
    )


def _status(st: BackupStatus, destinations_total: int) -> StatusInfo:
    local_root = str((settings.backups.local_root or settings.data_dir.expanduser() / "backups").expanduser())
    return StatusInfo(
        settings=_settings(st.settings, passphrase_set=st.passphrase_set),
        next_run_at=st.next_run_at,
        last_scheduled_at=st.last_scheduled_at,
        running=_run(st.running) if st.running else None,
        last_run=_run(st.last_run) if st.last_run else None,
        local_root=local_root,
        destinations_total=destinations_total,
    )


def _input(body: DestinationBody) -> DestinationInput:
    spec = DestinationSpec(
        name=body.name,
        kind=DestinationKind(body.kind),
        endpoint=body.endpoint,
        region=body.region,
        bucket=body.bucket,
        prefix=body.prefix,
        path_style=body.path_style,
        local_path=body.local_path,
    )
    return DestinationInput(
        spec=spec,
        access_key=(body.access_key or "").strip() or None,
        secret_key=(body.secret_key or "").strip() or None,
        make_default=body.make_default,
    )


def _check(result: CheckResult) -> CheckResultInfo:
    return CheckResultInfo(
        ok=result.ok, error=result.error, warnings=list(result.warnings), checked_at=result.checked_at
    )


def restore_command(destination: BackupDestination, backup_id: str) -> str:
    """Готовая команда восстановления для подсказки в админке: секретов в ней нет, ключи берутся из окружения."""
    spec = destination.spec
    if spec.kind is DestinationKind.local:
        root = (settings.backups.local_root or settings.data_dir.expanduser() / "backups").expanduser()
        path = root / (spec.local_path or "") / backup_id
        return f"hse-doc-studio backup restore --from-dir {shlex.quote(str(path))}"
    parts = ["hse-doc-studio", "backup", "restore", "--s3-bucket", spec.bucket or ""]
    if spec.endpoint:
        parts += ["--s3-endpoint", spec.endpoint]
    parts += ["--s3-region", spec.region]
    if spec.prefix:
        parts += ["--s3-prefix", spec.prefix]
    if spec.path_style:
        parts.append("--s3-path-style")
    parts += ["--backup-id", backup_id]
    return " ".join(shlex.quote(p) for p in parts)


def _stored(destination: BackupDestination, item: StoredBackup) -> StoredBackupInfo:
    m = item.manifest
    return StoredBackupInfo(
        backup_id=item.backup_id,
        created_at=m.created_at,
        app_version=m.app_version,
        schema_revision=m.schema_revision,
        installation_id=m.installation_id,
        encryption_mode=m.encryption_mode.value,
        size=m.total_size,
        parts=[StoredBackupPart(name=p.name, size=p.size, plain_size=p.plain_size) for p in m.parts],
        manifest_sha256=item.manifest_sha256,
        restore_command=restore_command(destination, item.backup_id),
    )


@router.get("/status", response_model=StatusInfo)
async def get_status(request: Request, response: Response) -> StatusInfo:
    response.headers.update(_NO_STORE)
    c = request.state.dishka_container
    actor = require_actor()
    st = await (await c.get(GetBackupSettingsUC)).execute(actor)
    listed = await (await c.get(ListDestinationsUC)).execute(actor)
    return _status(st, len(listed))


@router.put("/settings", response_model=StatusInfo)
async def put_settings(body: SettingsBody, request: Request, response: Response) -> StatusInfo:
    response.headers.update(_NO_STORE)
    c = request.state.dishka_container
    actor = require_actor()
    new = BackupSettings(
        enabled=body.enabled,
        schedule=Schedule(
            kind=ScheduleKind(body.schedule_kind), interval_hours=body.interval_hours, cron=body.cron.strip()
        ),
        keep_last=body.keep_last,
        keep_days=body.keep_days,
        encryption_mode=EncryptionMode(body.encryption_mode),
        notify_admins=body.notify_admins,
    )
    passphrase = body.passphrase if body.passphrase else None
    st = await (await c.get(UpdateBackupSettingsUC)).execute(actor, new, passphrase=passphrase)
    listed = await (await c.get(ListDestinationsUC)).execute(actor)
    return _status(st, len(listed))


@router.get("/destinations", response_model=list[DestinationInfo])
async def list_destinations(request: Request, response: Response) -> list[DestinationInfo]:
    response.headers.update(_NO_STORE)
    listed = await (await request.state.dishka_container.get(ListDestinationsUC)).execute(require_actor())
    return [_destination(d) for d in listed]


@router.post("/destinations", response_model=DestinationInfo, status_code=status.HTTP_201_CREATED)
async def create_destination(body: DestinationBody, request: Request, response: Response) -> DestinationInfo:
    response.headers.update(_NO_STORE)
    created = await (await request.state.dishka_container.get(CreateDestinationUC)).execute(
        require_actor(), _input(body)
    )
    return _destination(created)


@router.post("/destinations/test", response_model=CheckResultInfo)
async def test_form(body: CheckDestinationBody, request: Request, response: Response) -> CheckResultInfo:
    response.headers.update(_NO_STORE)
    uc = await request.state.dishka_container.get(TestDestinationUC)
    result = await uc.execute(require_actor(), destination_id=body.destination_id, data=_input(body.destination))
    return _check(result)


@router.put("/destinations/{destination_id}", response_model=DestinationInfo)
async def update_destination(
    destination_id: str, body: DestinationBody, request: Request, response: Response
) -> DestinationInfo:
    response.headers.update(_NO_STORE)
    uc = await request.state.dishka_container.get(UpdateDestinationUC)
    return _destination(await uc.execute(require_actor(), destination_id, _input(body)))


@router.delete("/destinations/{destination_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_destination(destination_id: str, request: Request) -> Response:
    await (await request.state.dishka_container.get(DeleteDestinationUC)).execute(require_actor(), destination_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/destinations/{destination_id}/test", response_model=CheckResultInfo)
async def test_saved(destination_id: str, request: Request, response: Response) -> CheckResultInfo:
    response.headers.update(_NO_STORE)
    uc = await request.state.dishka_container.get(TestDestinationUC)
    return _check(await uc.execute(require_actor(), destination_id=destination_id, data=None))


@router.get("/destinations/{destination_id}/backups", response_model=list[StoredBackupInfo])
async def list_stored(destination_id: str, request: Request, response: Response) -> list[StoredBackupInfo]:
    response.headers.update(_NO_STORE)
    c = request.state.dishka_container
    actor = require_actor()
    items = await (await c.get(ListStoredBackupsUC)).execute(actor, destination_id)
    listed = await (await c.get(ListDestinationsUC)).execute(actor)
    destination = next(d for d in listed if d.id == destination_id)
    return [_stored(destination, item) for item in items]


@router.delete("/destinations/{destination_id}/backups/{backup_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_stored(destination_id: str, backup_id: str, request: Request) -> Response:
    await (await request.state.dishka_container.get(DeleteStoredBackupUC)).execute(
        require_actor(), destination_id, backup_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/runs", response_model=RunInfo, status_code=status.HTTP_202_ACCEPTED)
async def start_run(body: StartRunBody, request: Request, response: Response) -> RunInfo:
    response.headers.update(_NO_STORE)
    run = await (await request.state.dishka_container.get(StartBackupUC)).execute(require_actor(), body.destination_id)
    return _run(run)


@router.get("/runs", response_model=RunPage)
async def list_runs(
    request: Request, response: Response, params: Annotated[PageParams, Depends(page_params)]
) -> RunPage:
    response.headers.update(_NO_STORE)
    found = await (await request.state.dishka_container.get(ListRunsUC)).execute(require_actor(), params.window)
    return RunPage(items=[_run(r) for r in found.items], total=found.total, limit=params.limit, offset=params.offset)


@router.get("/runs/{run_id}", response_model=RunInfo)
async def get_run(run_id: str, request: Request, response: Response) -> RunInfo:
    response.headers.update(_NO_STORE)
    return _run(await (await request.state.dishka_container.get(GetRunUC)).execute(require_actor(), run_id))
