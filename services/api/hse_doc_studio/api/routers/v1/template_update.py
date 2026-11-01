"""Обновление проекта на новую версию шаблона (core.template_update).

Поток интерфейса: статус (что доступно) → план (dry-run, что станет с каждым
файлом) → дифф по файлу → применение с отпечатком плана → при желании отмена.
«Сравнить с шаблоном» и снятие файла с отслеживания работают и без обновления.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import UUID

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, HTTPException, Query

from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.schemas.template_update import (
    ApplyTemplateUpdateRequest,
    ApplyTemplateUpdateResponse,
    AvailableUpdateResponse,
    CompareWithTemplateResponse,
    RevertTemplateUpdateRequest,
    RevertTemplateUpdateResponse,
    SetTemplateTrackingRequest,
    TemplateDiffResponse,
    TemplateFileOpResponse,
    TemplateFileStateResponse,
    TemplateTrackingResponse,
    TemplateUpdatePlanRequest,
    TemplateUpdatePlanResponse,
    TemplateUpdateRecordResponse,
    TemplateUpdateStatusResponse,
    TemplateVersionInfoResponse,
    UpdateWarningResponse,
)
from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.enums import ConflictResolution
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.template_update.entities import FileOp, TemplateUpdateRecord
from hse_doc_studio.core.template_update.errors import (
    TemplateUpdateInProgressError,
    TemplateUpdateNotRevertibleError,
    TemplateUpdatePlanOutdatedError,
    TemplateVersionUnavailableError,
)
from hse_doc_studio.core.vcs.errors import VcsError
from hse_doc_studio.use_cases.template_update.apply_template_update import (
    ApplyTemplateUpdateInput,
    ApplyTemplateUpdateUC,
)
from hse_doc_studio.use_cases.template_update.compare_with_template import (
    CompareWithTemplateInput,
    CompareWithTemplateUC,
    GetTemplateFileDiffInput,
    GetTemplateFileDiffUC,
    TemplateDiffView,
)
from hse_doc_studio.use_cases.template_update.get_template_update_status import (
    AvailableUpdate,
    GetTemplateUpdateStatusInput,
    GetTemplateUpdateStatusUC,
)
from hse_doc_studio.use_cases.template_update.plan_template_update import (
    PlanTemplateUpdateInput,
    PlanTemplateUpdateUC,
)
from hse_doc_studio.use_cases.template_update.revert_template_update import (
    RevertTemplateUpdateInput,
    RevertTemplateUpdateUC,
)
from hse_doc_studio.use_cases.template_update.set_template_tracking import (
    SetTemplateTrackingInput,
    SetTemplateTrackingUC,
)

router = APIRouter(route_class=SafeDishkaRoute)

T = TypeVar("T")

# Ошибка → HTTP-статус. Порядок важен: более узкие типы раньше.
_ERROR_STATUS: tuple[tuple[type[Exception], int], ...] = (
    (NotFoundError, 404),
    (TemplateVersionUnavailableError, 404),
    (TemplateUpdatePlanOutdatedError, 409),
    (TemplateUpdateInProgressError, 409),
    (TemplateUpdateNotRevertibleError, 409),
    (VcsError, 409),
    (ValueError, 400),
)


async def _call(action: Callable[[], Awaitable[T]]) -> T:
    try:
        return await action()
    except Exception as exc:
        for error_type, status in _ERROR_STATUS:
            if isinstance(exc, error_type):
                raise HTTPException(status_code=status, detail=str(exc)) from exc
        raise


def _resolutions(raw: dict[str, str]) -> dict[str, ConflictResolution]:
    try:
        return {path: ConflictResolution(value) for path, value in raw.items()}
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=localized_error(f"Неизвестное решение конфликта: {exc}", f"Unknown conflict resolution: {exc}"),
        ) from exc


# ── mappers ──────────────────────────────────────────────────────────────────
def _map_version(version: TemplateVersion) -> TemplateVersionInfoResponse:
    return TemplateVersionInfoResponse(
        version=version.version,
        status=version.status.value,
        released_at=version.released_at,
        summary=version.summary,
        changes={lang: list(items) for lang, items in version.changes.items()},
        breaking_changes={lang: list(items) for lang, items in version.breaking_changes.items()},
        released=version.is_released,
        min_studio=version.min_studio,
    )


def _map_available(update: AvailableUpdate) -> AvailableUpdateResponse:
    return AvailableUpdateResponse(
        version=_map_version(update.version),
        update_class=update.update_class.value if update.update_class else None,
    )


def _map_record(record: TemplateUpdateRecord) -> TemplateUpdateRecordResponse:
    return TemplateUpdateRecordResponse(
        id=record.id,
        from_version=record.from_version,
        to_version=record.to_version,
        at=record.at,
        pre_commit=record.pre_commit,
        markers=list(record.markers),
        reverted=record.reverted,
        reverts=record.reverts,
    )


def _map_op(op: FileOp) -> TemplateFileOpResponse:
    return TemplateFileOpResponse(
        path=op.path,
        action=op.action.value,
        binary=op.binary,
        doc_id=op.doc_id,
        conflicts=op.conflicts,
        approximate_base=op.approximate_base,
        resolutions=[r.value for r in op.allowed_resolutions()],
    )


# ── reads ────────────────────────────────────────────────────────────────────
@router.get("/projects/{project_id}/template-update", response_model=TemplateUpdateStatusResponse)
async def get_template_update_status(
    project_id: UUID, uc: FromDishka[GetTemplateUpdateStatusUC]
) -> TemplateUpdateStatusResponse:
    result = await _call(lambda: uc.execute(GetTemplateUpdateStatusInput(project_id=project_id)))
    return TemplateUpdateStatusResponse(
        current_version=result.project.lock.version,
        current=_map_version(result.current) if result.current is not None else None,
        digest_mismatch=result.digest_mismatch,
        available=[_map_available(u) for u in result.available],
        recommended=_map_available(result.recommended) if result.recommended is not None else None,
        last_update=_map_record(result.last_update) if result.last_update is not None else None,
        unresolved_markers=result.unresolved_markers,
        in_progress=result.in_progress,
    )


@router.get("/projects/{project_id}/template-update/diff", response_model=TemplateDiffResponse)
async def get_template_file_diff(
    project_id: UUID,
    uc: FromDishka[GetTemplateFileDiffUC],
    path: str = Query(...),
    view: TemplateDiffView = Query(default=TemplateDiffView.mine),
    to_version: str | None = Query(default=None),
    resolution: ConflictResolution | None = Query(default=None),
) -> TemplateDiffResponse:
    result = await _call(
        lambda: uc.execute(
            GetTemplateFileDiffInput(
                project_id=project_id, path=path, view=view, to_version=to_version, resolution=resolution
            )
        )
    )
    return TemplateDiffResponse(path=result.path, binary=result.binary, patch=result.patch, truncated=result.truncated)


@router.get("/projects/{project_id}/template/compare", response_model=CompareWithTemplateResponse)
async def compare_with_template(project_id: UUID, uc: FromDishka[CompareWithTemplateUC]) -> CompareWithTemplateResponse:
    result = await _call(lambda: uc.execute(CompareWithTemplateInput(project_id=project_id)))
    return CompareWithTemplateResponse(
        version=result.version,
        provenance=result.provenance.value,
        files=[
            TemplateFileStateResponse(
                path=f.path,
                status=f.status.value,
                doc_id=f.doc_id,
                binary=f.binary,
                approximate=f.approximate,
                ignored=f.ignored,
            )
            for f in result.files
        ],
    )


# ── writes ───────────────────────────────────────────────────────────────────
@router.post("/projects/{project_id}/template-update/plan", response_model=TemplateUpdatePlanResponse)
async def plan_template_update(
    project_id: UUID, body: TemplateUpdatePlanRequest, uc: FromDishka[PlanTemplateUpdateUC]
) -> TemplateUpdatePlanResponse:
    result = await _call(lambda: uc.execute(PlanTemplateUpdateInput(project_id=project_id, to_version=body.to_version)))
    plan = result.planned.plan
    return TemplateUpdatePlanResponse(
        from_version=plan.from_version,
        to_version=plan.to_version,
        update_class=plan.update_class.value if plan.update_class else None,
        provenance=plan.provenance.value,
        fingerprint=plan.fingerprint,
        counts={action.value: count for action, count in plan.counts.items()},
        files=[_map_op(op) for op in plan.ops],
        warnings=[UpdateWarningResponse(code=w.code.value, doc_ids=list(w.doc_ids)) for w in plan.warnings],
    )


@router.post("/projects/{project_id}/template-update/apply", response_model=ApplyTemplateUpdateResponse)
async def apply_template_update(
    project_id: UUID, body: ApplyTemplateUpdateRequest, uc: FromDishka[ApplyTemplateUpdateUC]
) -> ApplyTemplateUpdateResponse:
    resolutions = _resolutions(body.resolutions)
    result = await _call(
        lambda: uc.execute(
            ApplyTemplateUpdateInput(
                project_id=project_id,
                to_version=body.to_version,
                fingerprint=body.fingerprint,
                resolutions=resolutions,
            )
        )
    )
    return ApplyTemplateUpdateResponse(
        record=_map_record(result.record),
        written=result.written,
        deleted=result.deleted,
        markers=result.markers,
    )


@router.post("/projects/{project_id}/template-update/revert", response_model=RevertTemplateUpdateResponse)
async def revert_template_update(
    project_id: UUID, body: RevertTemplateUpdateRequest, uc: FromDishka[RevertTemplateUpdateUC]
) -> RevertTemplateUpdateResponse:
    resolutions = _resolutions(body.resolutions)
    result = await _call(
        lambda: uc.execute(
            RevertTemplateUpdateInput(
                project_id=project_id, update_id=body.update_id, dry_run=body.dry_run, resolutions=resolutions
            )
        )
    )
    return RevertTemplateUpdateResponse(
        record=_map_record(result.record),
        files=[_map_op(op) for op in result.ops],
        applied=result.applied,
        kept=result.kept,
    )


@router.put("/projects/{project_id}/template/tracking", response_model=TemplateTrackingResponse)
async def set_template_tracking(
    project_id: UUID, body: SetTemplateTrackingRequest, uc: FromDishka[SetTemplateTrackingUC]
) -> TemplateTrackingResponse:
    result = await _call(
        lambda: uc.execute(SetTemplateTrackingInput(project_id=project_id, path=body.path, tracked=body.tracked))
    )
    return TemplateTrackingResponse(ignored=sorted(result.state.ignored))
