"""`/api/admin/runner-install/fleet`: предложение обновить все раннеры установки разом и ход этого обновления.

Гард админки задаёт `make_admin_router`. Раннеры обновляются теми же способами, что и по одному (см.
`admin_runner_install`), а этот маршрут только выбирает устаревшие, запускает их по очереди и показывает итог.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from hse_doc_studio.api.runner_commands import studio_base_url
from hse_doc_studio.api.schemas.runner_fleet import (
    FleetBatchInfo,
    FleetDismissRequest,
    FleetItemInfo,
    FleetPlanResponse,
    FleetRunnerInfo,
    FleetUpgradeRequest,
)
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.jobs.errors import RunnerNotFoundError
from hse_doc_studio.core.runner_install.fleet import FleetBatch, FleetPlan
from hse_doc_studio.use_cases.runner_install.fleet import FleetBusyError, FleetSelectionError, RunnerFleetService

router = APIRouter(prefix="/runner-install/fleet")

_NO_STORE = {"Cache-Control": "no-store"}


async def _service(request: Request) -> RunnerFleetService:
    return await request.state.dishka_container.get(RunnerFleetService)


def batch_info(batch: FleetBatch) -> FleetBatchInfo:
    return FleetBatchInfo(
        id=batch.id,
        state=batch.state.value,
        target_version=batch.target_version,
        created_at=batch.created_at,
        finished_at=batch.finished_at,
        cancel_requested=batch.cancel_requested,
        items=[
            FleetItemInfo(
                runner_id=i.runner_id,
                name=i.name,
                kind=i.kind.value,
                from_version=i.from_version,
                to_version=i.to_version,
                state=i.state.value,
                code=i.code,
                detail=i.detail,
                rolled_back=i.rolled_back,
            )
            for i in batch.items
        ],
    )


def plan_info(plan: FleetPlan) -> FleetPlanResponse:
    return FleetPlanResponse(
        server_version=plan.server_version,
        offer=plan.offer,
        dismissed_version=plan.dismissed_version,
        items=[
            FleetRunnerInfo(
                runner_id=c.runner_id,
                name=c.name,
                kind=c.kind.value,
                version=c.version,
                target_version=c.target_version,
                status=c.status,
                running_jobs=c.running_jobs,
                manual_reason=c.manual_reason.value if c.manual_reason else None,
            )
            for c in plan.items
        ],
        batch=batch_info(plan.batch) if plan.batch is not None else None,
    )


@router.get("", response_model=FleetPlanResponse)
async def fleet_plan(request: Request, response: Response) -> FleetPlanResponse:
    """Устаревшие раннеры установки (личные не в счёт) и можно ли обновить каждый отсюда."""
    response.headers.update(_NO_STORE)
    return plan_info(await (await _service(request)).plan(require_actor()))


@router.post("/upgrade", response_model=FleetBatchInfo, status_code=status.HTTP_202_ACCEPTED)
async def fleet_upgrade(body: FleetUpgradeRequest, request: Request, response: Response) -> FleetBatchInfo:
    """Обновить выбранные раннеры по одному; ход читается `GET /batches/{id}`.

    409 `fleet_busy`: общий запуск уже идёт. 422 `input_invalid`: в выборе раннер, которого нет среди устаревших или
    который нельзя обновить отсюда (`runner_ids` в ответе).
    """
    response.headers.update(_NO_STORE)
    try:
        batch = await (await _service(request)).start(
            require_actor(), body.runner_ids, studio_url=studio_base_url(request)
        )
    except FleetBusyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "fleet_busy"}) from exc
    except FleetSelectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "input_invalid", "field": "runner_ids", "runner_ids": exc.runner_ids},
        ) from exc
    return batch_info(batch)


@router.post("/dismiss", status_code=status.HTTP_204_NO_CONTENT)
async def fleet_dismiss(body: FleetDismissRequest, request: Request) -> Response:
    """Отказаться от предложения для этой версии Студии: для всех админов, до следующей версии."""
    await (await _service(request)).dismiss(require_actor(), body.version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/batches/{batch_id}", response_model=FleetBatchInfo)
async def fleet_batch(batch_id: str, request: Request, response: Response) -> FleetBatchInfo:
    response.headers.update(_NO_STORE)
    batch = (await _service(request)).batch(require_actor(), batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    return batch_info(batch)


@router.post("/batches/{batch_id}/cancel", response_model=FleetBatchInfo)
async def fleet_cancel(batch_id: str, request: Request, response: Response) -> FleetBatchInfo:
    """Остановить после текущего раннера: идущее обновление доделывается, остальные пропускаются."""
    response.headers.update(_NO_STORE)
    try:
        batch = await (await _service(request)).cancel(require_actor(), batch_id)
    except RunnerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found") from exc
    return batch_info(batch)
