from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class DocumentVariantResponse(BaseModel):
    id: str
    label: dict[str, str]
    source_file: str | None = None
    output_file: str | None = None
    # Языки проекта, в которых вариант можно выбрать (IEEE/ISO-редакции — [en]).
    # Пустой список → доступен во всех языках.
    supported_langs: list[str] = []


class TemplateInfoResponse(BaseModel):
    id: str
    name: dict[str, str]
    short_name: dict[str, str]
    icon: str
    accent_hue: int
    default_version: str


class PackResponse(BaseModel):
    id: str
    name: dict[str, str]
    description: dict[str, str]
    maintainer: dict[str, str]
    templates: list[TemplateInfoResponse]


class VersionListItemResponse(BaseModel):
    version: str
    status: str
    released_at: str  # date as ISO string
    summary: dict[str, str]
    is_default: bool


class SignatureSlotResponse(BaseModel):
    id: str
    label: dict[str, str]
    applies_to: list[str]
    # Обязательности здесь нет: она зависит от контрольной точки, а каталог
    # описывает пак вне проекта. Смотреть GET /projects/{id}/signatures →
    # runtime_slots[].required_by.
    # {page: int, x_mm, y_mm, width_mm: float}
    default_placement: dict[str, float]
    # Team mode: слот размножается по авторам (рантайм-слоты "id--slug").
    per_author: bool = False


class DocumentDefinitionResponse(BaseModel):
    id: str
    name: dict[str, str]
    code: dict[str, str]
    required: bool
    source_file: str | None = None
    output_file: str | None = None
    gost_ref: str | None = None
    # ISO-639-1 language codes for which this document is actually authored.
    # Empty list means "no explicit declaration" — frontend should treat that
    # as "available for every language the template supports".
    supported_langs: list[str] = []
    variants: list[DocumentVariantResponse]
    # Team mode: "personal" — экземпляр на автора; "shared" — один на проект.
    scope: str = "shared"
    # В каких режимах состава документ существует (общее ТЗ — только team).
    supported_staffing: list[str] = ["solo", "team"]
    # В каких видах работы документ существует: "research" (Аннотация) и/или
    # "project" (ЕСПД-доки). Пусто/оба = документ есть в любом виде.
    supported_kinds: list[str] = ["research", "project"]


class MetaFieldResponse(BaseModel):
    type: str
    label: dict[str, str]
    placeholder: str | None
    required_at: str
    help: dict[str, str] | None
    # Static pre-fill the wizard seeds into the field when left blank.
    default: Any | None = None
    # Computed pre-fill kind (e.g. "academic_year"); the wizard resolves it.
    auto: str | None = None
    options: list[str]
    # Id of a meta_groups entry (display grouping in settings), if declared.
    group: str | None = None
    # "project" — одно значение на проект; "author" — своё у каждого автора
    # (редактируется в карточке автора, живёт в author.meta).
    scope: str = "project"
    # Виды работы, в которых поле показывается (research/project); пусто/оба = все.
    supported_kinds: list[str] = ["research", "project"]


class MetaGroupResponse(BaseModel):
    id: str
    label: dict[str, str]
    # Страница настроек проекта: "meta" (по умолчанию) или "documents".
    section: str = "meta"


class SubmissionDocItemResponse(BaseModel):
    doc_id: str
    signatures: list[str]
    # Гейты состава, которые применяет SubmissionService.build_item_list. Отдаём
    # их наружу: сам ДОКУМЕНТ может существовать в проекте, а в комплект точки не
    # входить (thesis на КТ2 ВКР — только проектный формат; Текст программы не
    # сдаётся под NDA). Без этих полей клиент считает пункт обязательным и
    # показывает блокер, которого при сборке пакета не будет.
    skip_if_nda: bool = False
    supported_kinds: list[str] = ["research", "project"]


class SubmissionExtraItemResponse(BaseModel):
    source: str
    output_name: str
    format: str | None = None
    # Тот же гейт, что у пунктов-документов: extra попадает в пакет не во всех
    # видах работы («Ссылка на код.txt» на КТ2 — только research). Без поля
    # клиент считает анкету обязательной там, где её в архиве не будет.
    supported_kinds: list[str] = ["research", "project"]


class SubmissionProfileResponse(BaseModel):
    id: str
    name: dict[str, str]
    description: dict[str, str]
    items: list[SubmissionDocItemResponse]
    extra_items: list[SubmissionExtraItemResponse]


class VersionDetailResponse(BaseModel):
    version: str
    status: str
    engine_config: dict[str, Any]  # {"default": "xelatex", "allowed": [...], "passes": 3}
    documents: list[DocumentDefinitionResponse]
    meta_fields: dict[str, MetaFieldResponse]
    # Display order of meta-field groups; fields reference them via `group`.
    meta_groups: list[MetaGroupResponse] = []
    signatures: dict[str, Any]  # {"slots": [...]}
    pack_submission: dict[str, Any]  # {"profiles": [...]}
    # Какие режимы состава поддерживает шаблон; визард блокирует team-создание
    # по пакам без "team".
    supported_staffing: list[str] = ["solo"]
