from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class FormOptionResponse(BaseModel):
    id: str
    label: dict[str, str]
    default: bool = False


class FormColumnResponse(BaseModel):
    id: str
    label: dict[str, str]


class VisibleIfResponse(BaseModel):
    field: str
    equals: Any = None


class FormFieldResponse(BaseModel):
    id: str
    type: str
    label: dict[str, str]
    help: dict[str, str] | None = None
    placeholder: dict[str, str] | None = None
    required: bool = False
    options: list[FormOptionResponse] = []
    columns: list[FormColumnResponse] = []
    min: float | None = None
    max: float | None = None
    step: float | None = None
    min_length: int | None = None
    default: Any = None
    widget: str | None = None
    visible_if: VisibleIfResponse | None = None
    content: dict[str, str] | None = None


class FormSectionResponse(BaseModel):
    id: str
    title: dict[str, str]
    fields: list[FormFieldResponse]


class FormErrorResponse(BaseModel):
    field_id: str
    message: str


class FormResponse(BaseModel):
    id: str
    title: dict[str, str]
    schema_version: int
    required_for_pack: bool
    sections: list[FormSectionResponse]
    # Raw saved answers: field_id -> value (shape governed by the field types).
    answers: dict[str, Any]
    # `completed` = student signed off; `complete` = all required fields valid.
    completed: bool
    complete: bool
    errors: list[FormErrorResponse]


class FormListItemResponse(BaseModel):
    id: str
    title: dict[str, str]
    required_for_pack: bool
    completed: bool
    complete: bool
    # Presentational icon hint from the pack (e.g. "bot", "clipboard"); the
    # frontend maps it to a concrete icon. None → generic form icon.
    icon: str | None = None
    # Team mode: слаг автора-владельца инстанса per-author формы (None — общая).
    owner: str | None = None


class FormListResponse(BaseModel):
    forms: list[FormListItemResponse]


class UpdateFormRequest(BaseModel):
    # PATCH-style: omitted (None) fields keep the currently saved value.
    completed: bool | None = None
    answers: dict[str, Any] | None = None


class FormPreviewResponse(BaseModel):
    output_name: str
    format: str
    content: str
