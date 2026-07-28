from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException

from hse_doc_studio.api.schemas.forms import (
    FormColumnResponse,
    FormErrorResponse,
    FormFieldResponse,
    FormListItemResponse,
    FormListResponse,
    FormOptionResponse,
    FormPreviewResponse,
    FormResponse,
    FormSectionResponse,
    UpdateFormRequest,
    VisibleIfResponse,
)
from hse_doc_studio.core.catalog import FormDefinition, FormFieldDef
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.value_objects import FormState, FormValidationError
from hse_doc_studio.use_cases.forms.get_form import GetFormInput, GetFormUC
from hse_doc_studio.use_cases.forms.list_forms import ListFormsInput, ListFormsUC
from hse_doc_studio.use_cases.forms.render_form import RenderFormInput, RenderFormUC
from hse_doc_studio.use_cases.forms.update_form import UpdateFormInput, UpdateFormUC

router = APIRouter(route_class=DishkaRoute)


def _map_field(f: FormFieldDef) -> FormFieldResponse:
    return FormFieldResponse(
        id=f.id,
        type=str(f.type),
        label=f.label,
        help=f.help,
        placeholder=f.placeholder,
        required=f.required,
        options=[FormOptionResponse(id=o.id, label=o.label, default=o.default) for o in f.options],
        columns=[FormColumnResponse(id=c.id, label=c.label) for c in f.columns],
        min=f.min,
        max=f.max,
        step=f.step,
        min_length=f.min_length,
        default=f.default,
        widget=f.widget,
        visible_if=(
            VisibleIfResponse(field=f.visible_if.field, equals=f.visible_if.equals)
            if f.visible_if is not None
            else None
        ),
        content=f.content,
    )


def _map_form(
    form: FormDefinition,
    state: FormState,
    complete: bool,
    errors: list[FormValidationError],
) -> FormResponse:
    return FormResponse(
        id=form.id,
        title=form.title,
        schema_version=form.schema_version,
        required_for_pack=form.required_for_pack,
        sections=[
            FormSectionResponse(
                id=s.id,
                title=s.title,
                fields=[_map_field(f) for f in s.fields],
            )
            for s in form.sections
        ],
        answers=state.answers,
        completed=state.completed,
        complete=complete,
        errors=[FormErrorResponse(field_id=e.field_id, message=e.message) for e in errors],
    )


@router.get("/projects/{project_id}/forms", response_model=FormListResponse)
async def list_forms(
    project_id: UUID,
    uc: FromDishka[ListFormsUC],
) -> FormListResponse:
    try:
        result = await uc.execute(ListFormsInput(project_id=project_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FormListResponse(
        forms=[
            FormListItemResponse(
                id=f.id,
                title=f.title,
                required_for_pack=f.required_for_pack,
                completed=f.completed,
                complete=f.complete,
                icon=f.icon,
                owner=f.owner,
            )
            for f in result.forms
        ]
    )


@router.get("/projects/{project_id}/forms/{form_id}", response_model=FormResponse)
async def get_form(
    project_id: UUID,
    form_id: str,
    uc: FromDishka[GetFormUC],
) -> FormResponse:
    try:
        result = await uc.execute(GetFormInput(project_id=project_id, form_id=form_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_form(result.form, result.state, result.complete, result.errors)


@router.put("/projects/{project_id}/forms/{form_id}", response_model=FormResponse)
async def update_form(
    project_id: UUID,
    form_id: str,
    body: UpdateFormRequest,
    uc: FromDishka[UpdateFormUC],
) -> FormResponse:
    try:
        result = await uc.execute(
            UpdateFormInput(
                project_id=project_id,
                form_id=form_id,
                completed=body.completed,
                answers=body.answers,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_form(result.form, result.state, result.complete, result.errors)


@router.get("/projects/{project_id}/forms/{form_id}/preview", response_model=FormPreviewResponse)
async def preview_form(
    project_id: UUID,
    form_id: str,
    uc: FromDishka[RenderFormUC],
) -> FormPreviewResponse:
    try:
        result = await uc.execute(RenderFormInput(project_id=project_id, form_id=form_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FormPreviewResponse(
        output_name=result.output_name,
        format=result.format,
        content=result.content,
    )
