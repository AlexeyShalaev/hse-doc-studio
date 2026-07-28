from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException

from hse_doc_studio.api.schemas.requirements import (
    RequirementEntryResponse,
    RequirementFormatSchema,
    RequirementsMatrixResponse,
    UpdateRequirementsFormatRequest,
)
from hse_doc_studio.core.enums import RequirementFormatKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.value_objects import RequirementsFormat
from hse_doc_studio.use_cases.requirements.get_requirements import (
    GetRequirementsInput,
    GetRequirementsOutput,
    GetRequirementsUC,
)
from hse_doc_studio.use_cases.requirements.update_requirements_format import (
    UpdateRequirementsFormatInput,
    UpdateRequirementsFormatUC,
)

router = APIRouter(route_class=DishkaRoute)


def _fmt_to_schema(fmt: RequirementsFormat) -> RequirementFormatSchema:
    return RequirementFormatSchema(
        kind=str(fmt.kind),
        id_pattern=fmt.id_pattern,
        definition_docs=list(fmt.definition_docs),
        def_pattern=fmt.def_pattern,
        ref_pattern=fmt.ref_pattern,
    )


def _schema_to_fmt(schema: RequirementFormatSchema) -> RequirementsFormat:
    return RequirementsFormat(
        kind=RequirementFormatKind(schema.kind),
        id_pattern=schema.id_pattern,
        definition_docs=tuple(schema.definition_docs),
        def_pattern=schema.def_pattern,
        ref_pattern=schema.ref_pattern,
    )


def _matrix_response(result: GetRequirementsOutput) -> RequirementsMatrixResponse:
    return RequirementsMatrixResponse(
        items=[
            RequirementEntryResponse(
                id=r.id,
                title=r.title,
                source=r.source,
                referenced_in=r.referenced_in,
                status=r.status,
            )
            for r in result.items
        ],
        format=_fmt_to_schema(result.requirements_format),
        format_overridden=result.overridden,
    )


@router.get(
    "/projects/{project_id}/requirements",
    response_model=RequirementsMatrixResponse,
)
async def get_requirements(
    project_id: UUID,
    uc: FromDishka[GetRequirementsUC],
) -> RequirementsMatrixResponse:
    try:
        result = await uc.execute(GetRequirementsInput(project_id=project_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _matrix_response(result)


@router.put(
    "/projects/{project_id}/requirements/format",
    response_model=RequirementsMatrixResponse,
)
async def update_requirements_format(
    project_id: UUID,
    body: UpdateRequirementsFormatRequest,
    update_uc: FromDishka[UpdateRequirementsFormatUC],
    get_uc: FromDishka[GetRequirementsUC],
) -> RequirementsMatrixResponse:
    fmt = _schema_to_fmt(body.format) if body.format is not None else None
    try:
        await update_uc.execute(UpdateRequirementsFormatInput(project_id=project_id, requirements_format=fmt))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        # Invalid regex / missing required pattern fields → bad request.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = await get_uc.execute(GetRequirementsInput(project_id=project_id))
    return _matrix_response(result)
