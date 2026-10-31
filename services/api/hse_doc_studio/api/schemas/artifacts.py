"""Контракт артефактов проекта: PDF, выгруженные локальной Студией (docs/design/local-sync.md, раздел 2)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from hse_doc_studio.api.schemas.common import StrictModel


class ProjectArtifactResponse(StrictModel):
    id: str
    kind: Literal["pdf"]
    doc_id: str
    file_name: str
    size: int
    sha256: str
    pages: int | None
    source_commit: str | None
    built_at: datetime | None
    uploaded_at: datetime
    uploaded_by_name: str | None
    client_name: str | None
    # Относительный адрес файла: открывается теми же правами, что и проект.
    file_url: str


class ProjectArtifactListResponse(StrictModel):
    items: list[ProjectArtifactResponse]
    # Предел размера и число хранимых версий: интерфейс подсказывает, что будет с загрузкой.
    max_pdf_bytes: int
    keep_per_document: int


class PdfUploadResponse(StrictModel):
    artifact: ProjectArtifactResponse
    # false: такой же файл уже был последним, новая запись не создана.
    created: bool
