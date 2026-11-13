from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel

from hse_doc_studio.api.schemas.common import StrictModel


class TemplateVersionInfoResponse(BaseModel):
    version: str
    status: str
    released_at: date
    summary: dict[str, str]
    # Заметки версии по языкам интерфейса (`changes:` version.yaml).
    changes: dict[str, list[str]]
    breaking_changes: dict[str, list[str]]
    # Версия внесена в реестр выпусков: её содержимое неизменно.
    released: bool
    min_studio: str | None


class AvailableUpdateResponse(BaseModel):
    version: TemplateVersionInfoResponse
    # patch | minor | major | null (номер не разобран)
    update_class: str | None


class TemplateUpdateRecordResponse(BaseModel):
    id: str
    from_version: str
    to_version: str
    at: str
    pre_commit: str
    markers: list[str]
    reverted: bool
    reverts: str | None


class TemplateUpdateStatusResponse(BaseModel):
    current_version: str
    current: TemplateVersionInfoResponse | None
    digest_mismatch: bool
    available: list[AvailableUpdateResponse]
    recommended: AvailableUpdateResponse | None
    last_update: TemplateUpdateRecordResponse | None
    unresolved_markers: list[str]
    in_progress: bool


class TemplateFileOpResponse(BaseModel):
    path: str
    # update | merge | conflict | add | delete | orphan | user_deleted | ignored
    action: str
    binary: bool
    doc_id: str | None
    conflicts: int
    approximate_base: bool
    # Допустимые решения для конфликта: mine | theirs | markers.
    resolutions: list[str]


class UpdateWarningResponse(BaseModel):
    code: str
    doc_ids: list[str]


class TemplateUpdatePlanRequest(BaseModel):
    to_version: str


class SignaturePresetPlaceResponse(StrictModel):
    doc_id: str
    slot_id: str
    # Место новой версии на якоре шаблона, а якоря текущей сборки неизвестны (signing-route.md, 15.17.10): место
    # встанет по строке шаблона после сборки.
    after_build: bool = False


class SignaturePresetKeptResponse(StrictModel):
    doc_id: str
    slot_id: str
    # manual: место изменено автором; route: документ на подписании; signed: над зафиксированным PDF есть ЭП.
    reason: Literal["manual", "route", "signed"]


class SignaturePresetsResponse(StrictModel):
    """Места подписей из шаблона на новой версии (signing-route.md, 15.9 и 15.11)."""

    updated: list[SignaturePresetPlaceResponse]
    kept: list[SignaturePresetKeptResponse]


class TemplateUpdatePlanResponse(StrictModel):
    from_version: str
    to_version: str
    update_class: str | None
    # recorded | root | approximate — откуда взялась база слияния.
    provenance: str
    fingerprint: str
    counts: dict[str, int]
    files: list[TemplateFileOpResponse]
    warnings: list[UpdateWarningResponse]
    # Пустые `files` при непустом `updated` это не «нечего обновлять»: файлы не меняются, места подписей обновятся.
    signature_presets: SignaturePresetsResponse


class ApplyTemplateUpdateRequest(BaseModel):
    to_version: str
    fingerprint: str
    # Путь → mine | theirs | markers; конфликт без решения остаётся «моим».
    resolutions: dict[str, str] = {}


class ApplyTemplateUpdateResponse(BaseModel):
    record: TemplateUpdateRecordResponse
    written: list[str]
    deleted: list[str]
    markers: list[str]


class RevertTemplateUpdateRequest(BaseModel):
    update_id: str | None = None
    dry_run: bool = False
    resolutions: dict[str, str] = {}


class RevertTemplateUpdateResponse(BaseModel):
    record: TemplateUpdateRecordResponse
    files: list[TemplateFileOpResponse]
    applied: bool
    kept: list[str]


class TemplateDiffResponse(BaseModel):
    path: str
    binary: bool
    patch: str
    truncated: bool


class TemplateFileStateResponse(BaseModel):
    path: str
    # modified | deleted
    status: str
    doc_id: str | None
    binary: bool
    approximate: bool
    ignored: bool


class CompareWithTemplateResponse(BaseModel):
    version: str
    provenance: str
    files: list[TemplateFileStateResponse]


class SetTemplateTrackingRequest(BaseModel):
    path: str
    tracked: bool


class TemplateTrackingResponse(BaseModel):
    ignored: list[str]
