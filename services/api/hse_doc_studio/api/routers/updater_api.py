"""Протокол апдейтера `/api/updater/v1`. Подлинность проверяет сам маршрут по общему секрету (Bearer)."""

from __future__ import annotations

import hmac
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.rate_limit import enforce_ip
from hse_doc_studio.api.schemas.server_update import (
    UpdaterEventBody,
    UpdaterEventOut,
    UpdaterPollBody,
    UpdaterPollOut,
    UpdaterRunSpec,
)
from hse_doc_studio.core.rate_limit import AUTH_IP
from hse_doc_studio.core.server_update.entities import RunStatus
from hse_doc_studio.core.server_update.errors import UpdateError, UpdateErrorCode
from hse_doc_studio.use_cases.server_update.service import EventReport, PollReport, UpdateService

UPDATER_API_PREFIX = "/api/updater/v1"

router = APIRouter(prefix=UPDATER_API_PREFIX, tags=["updater"], dependencies=[Depends(require_server_mode)])


async def _authorize(request: Request) -> None:
    """Секрет сравнивается за постоянное время; перебор режется по IP. Пустой секрет закрывает протокол целиком."""
    await enforce_ip(request, AUTH_IP)
    expected = settings.server_update.updater_token.get_secret_value()
    scheme, _, given = request.headers.get("Authorization", "").partition(" ")
    ok = (
        bool(expected) and scheme.lower() == "bearer" and hmac.compare_digest(given.strip().encode(), expected.encode())
    )
    if not ok or not settings.server_update.enabled:
        raise UpdateError(UpdateErrorCode.unauthorized, "invalid updater token")


@router.post("/poll", response_model=UpdaterPollOut)
async def poll(body: UpdaterPollBody, request: Request) -> UpdaterPollOut:
    """Апдейтер спрашивает работу. Запрос служит и признаком жизни; занятый апдейтер работу не получает."""
    await _authorize(request)
    service = await request.state.dishka_container.get(UpdateService)
    spec = await service.poll(PollReport(updater_version=body.updater_version, busy=body.busy))
    if spec is None:
        return UpdaterPollOut(run=None)
    return UpdaterPollOut(
        run=UpdaterRunSpec(
            run_id=spec.run_id,
            kind=spec.kind.value,
            from_version=spec.from_version,
            to_version=spec.to_version,
            verify=spec.verify.value,
            digests_url=spec.digests_url,
            restore_db=spec.restore_db,
        )
    )


@router.post("/runs/{run_id}/events", response_model=UpdaterEventOut)
async def post_event(
    body: UpdaterEventBody,
    request: Request,
    run_id: UUID = Path(),  # noqa: B008
) -> UpdaterEventOut:
    await _authorize(request)
    service = await request.state.dishka_container.get(UpdateService)
    run = await service.report(
        str(run_id),
        EventReport(
            seq=body.seq,
            at=body.at,
            phase=body.phase,
            level=body.level,
            message=body.message,
            status=RunStatus(body.status) if body.status else None,
            from_revision=body.from_revision,
            to_revision=body.to_revision,
            db_restored=body.db_restored,
            error_code=body.error_code,
        ),
    )
    return UpdaterEventOut(status=run.status.value, last_seq=run.last_seq)
