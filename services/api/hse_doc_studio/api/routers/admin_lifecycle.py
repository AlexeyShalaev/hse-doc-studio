"""`/api/admin/data-lifecycle`: сроки хранения, размеры источников роста, запуск очистки, пороги места."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from hse_doc_studio.api.schemas.lifecycle import (
    LifecycleLastRun,
    LifecycleOverviewBody,
    LifecycleRunBody,
    LifecycleSource,
    LifecycleVolume,
    StorageThresholdsBody,
    UpdateRetentionRequest,
)
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.lifecycle.disk import StorageLevel
from hse_doc_studio.use_cases.lifecycle.admin import (
    GetLifecycleUC,
    LifecycleOverview,
    RunLifecycleUC,
    SourceView,
    UpdateRetentionUC,
    UpdateThresholdsUC,
)

router = APIRouter(prefix="/data-lifecycle")

_NO_STORE = {"Cache-Control": "no-store"}


def _actor() -> Actor:
    actor = current_actor()
    if actor is None:
        raise IdentityError(IdentityErrorCode.auth_required)
    return actor


def _last_run(view: SourceView) -> LifecycleLastRun | None:
    if view.last_run is not None:
        r = view.last_run
        return LifecycleLastRun(
            at=r.last_run_at,
            duration_ms=r.last_duration_ms,
            removed=r.last_removed,
            error=r.last_error,
            runs=r.runs,
            total_removed=r.total_removed,
        )
    if view.task is not None and view.task.last_run_at is not None:
        t = view.task
        error = "task_failed" if t.failures and t.failures >= t.runs else None
        return LifecycleLastRun(
            at=t.last_run_at, duration_ms=None, removed=None, error=error, runs=t.runs, total_removed=None
        )
    return None


def _source(view: SourceView) -> LifecycleSource:
    p = view.policy
    b = p.bounds
    return LifecycleSource(
        key=p.key,
        group=p.group.value,
        strategy=p.strategy.value,
        growth=p.growth,
        days=view.days,
        days_source=view.days_source,
        min_days=b.min_days if b else None,
        max_days=b.max_days if b else None,
        default_days=b.default_days if b else None,
        editable=p.editable,
        run_now=p.run_now and p.strategy.value in {"partition_drop", "delete_batches", "file_sweep"},
        protected=p.protected,
        env=p.env,
        bytes=view.size.bytes if view.size else None,
        rows=view.size.rows if view.size else None,
        partitions=view.size.partitions if view.size else None,
        last_run=_last_run(view),
    )


def _overview(view: LifecycleOverview) -> LifecycleOverviewBody:
    return LifecycleOverviewBody(
        sources=[_source(s) for s in view.sources],
        volumes=[
            LifecycleVolume(
                name=v.usage.name,
                used_bytes=v.usage.used_bytes,
                total_bytes=v.usage.total_bytes,
                free_bytes=v.usage.free_bytes,
                used_ratio=v.usage.used_ratio,
                level=StorageLevel(v.level).name,
            )
            for v in view.volumes
        ],
        thresholds=StorageThresholdsBody(
            warn_percent=view.thresholds.warn_percent, critical_percent=view.thresholds.critical_percent
        ),
        level=StorageLevel(view.level).name,
        safe_mode=view.safe_mode,
    )


@router.get("", response_model=LifecycleOverviewBody)
async def get_lifecycle(request: Request, response: Response) -> LifecycleOverviewBody:
    response.headers.update(_NO_STORE)
    return _overview(await (await request.state.dishka_container.get(GetLifecycleUC)).execute(_actor()))


@router.put("/retention/{key}", response_model=LifecycleOverviewBody)
async def put_retention(
    key: str, body: UpdateRetentionRequest, request: Request, response: Response
) -> LifecycleOverviewBody:
    response.headers.update(_NO_STORE)
    container = request.state.dishka_container
    await (await container.get(UpdateRetentionUC)).execute(_actor(), key, body.days)
    return _overview(await (await container.get(GetLifecycleUC)).execute(_actor()))


@router.put("/thresholds", response_model=LifecycleOverviewBody)
async def put_thresholds(body: StorageThresholdsBody, request: Request, response: Response) -> LifecycleOverviewBody:
    response.headers.update(_NO_STORE)
    container = request.state.dishka_container
    await (await container.get(UpdateThresholdsUC)).execute(_actor(), body.warn_percent, body.critical_percent)
    return _overview(await (await container.get(GetLifecycleUC)).execute(_actor()))


@router.post("/{key}/run", response_model=LifecycleRunBody)
async def run_now(key: str, request: Request, response: Response) -> LifecycleRunBody:
    response.headers.update(_NO_STORE)
    outcome = await (await request.state.dishka_container.get(RunLifecycleUC)).execute(_actor(), key)
    return LifecycleRunBody(
        key=outcome.key,
        removed=outcome.removed,
        partitions_dropped=outcome.partitions_dropped,
        more=outcome.more,
        error=outcome.error,
    )
