from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from hse_doc_studio.api.schemas.catalog import SubmissionProfileResponse
from hse_doc_studio.api.schemas.signature_plan import PlanPinnedResponse

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


class SubmissionWarningResponse(BaseModel):
    """Предупреждение пакета без пропуска: файл в пакете есть (signing-route.md, 12.8).

    `changed_after_sent`: рабочая сборка документа разошлась с версией на подписи, в пакет попала версия на
    подписи. `pinned` та же версия, что у документа в плане подписей (`sha256` хэш файла версии, по которому
    собран пакет), `working_sha256` хэш рабочей сборки. Рядом интерфейс предлагает «Отправить новую версию».
    """

    code: Literal["changed_after_sent"]
    doc_id: str
    # Дата версии на подписи (ISO 8601, UTC), поле контракта W7 (12.9); то же, что `pinned.pinned_at`.
    sent_at: str
    # Имя файла документа в пакете.
    file: str
    # Готовый текст на языке интерфейса.
    message: str
    pinned: PlanPinnedResponse
    working_sha256: str


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
    # Только в ответе на создание пакета; список сдач их не хранит.
    warnings: list[SubmissionWarningResponse] = []
