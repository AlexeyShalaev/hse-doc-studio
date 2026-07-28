from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from hse_doc_studio.api.schemas.catalog import SubmissionProfileResponse

ArchiveFormat = Literal["zip", "targz", "7z", "rar"]


class SubmissionProfileListResponse(BaseModel):
    profiles: list[SubmissionProfileResponse]


class CreateSubmissionDocItem(BaseModel):
    doc_id: str
    signatures: list[str] = []


class CreateSubmissionExtraItem(BaseModel):
    source: str
    output_name: str
    format: str | None = None


class CreateSubmissionRequest(BaseModel):
    profile_id: str
    # Optional override of the profile composition; the backend falls back to
    # the profile's declared items/extras when these are empty.
    items: list[CreateSubmissionDocItem] = []
    extra_items: list[CreateSubmissionExtraItem] = []
    archive_format: ArchiveFormat = "zip"
    # Team mode: чей пакет формируем (личные доки автора + общие).
    # Обязателен для командных проектов.
    author_slug: str | None = None
    # doc_id (инстанс) -> конвертировать в PDF при упаковке? Только для доков
    # с custom_file конвертируемого формата (см. GET .../submissions/preflight).
    custom_doc_decisions: dict[str, bool] | None = None


class CustomDocPreviewItemResponse(BaseModel):
    doc_id: str
    doc_name: dict[str, str]
    original_filename: str
    ext: str
    convertible: bool
    default_decision: bool | None = None


class SubmissionRecordResponse(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    id: str
    profile_id: str
    profile_name: dict[str, str] | None = None
    created_at: datetime
    output_path: str
    # Unpacked folder of stamped PDFs that sits next to the archive; used by the
    # "open in editor" action. None for legacy records created before folders.
    output_dir: str | None = None
    size_bytes: int | None = None
    archive_format: str = "zip"
    doc_count: int = 0
