"""Артефакты проекта, выгруженные локальной Студией (docs/design/local-sync.md, раздел 2)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

PDF_MAGIC = b"%PDF-"
PDF_MEDIA_TYPE = "application/pdf"
# Идентификатор документа проекта попадает в ключ объекта: только безопасные символы.
_DOC_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


class ArtifactKind(StrEnum):
    pdf = "pdf"


class ArtifactErrorCode(StrEnum):
    too_large = "artifact_too_large"
    not_pdf = "artifact_not_pdf"
    checksum_mismatch = "artifact_checksum_mismatch"
    unknown_document = "artifact_unknown_document"
    forbidden = "artifact_forbidden"
    not_found = "artifact_not_found"
    read_only = "artifact_read_only"


class ArtifactError(Exception):
    """Отказ приёма или выдачи артефакта; `message` уже локализован."""

    def __init__(self, code: ArtifactErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ProjectArtifact:
    id: UUID
    project_id: UUID
    kind: ArtifactKind
    doc_id: str
    file_name: str
    size: int
    sha256: str
    object_key: str
    uploaded_at: datetime
    pages: int | None = None
    # Коммит локальной ветки на момент сборки: по нему видно, какой версии исходников соответствует PDF.
    source_commit: str | None = None
    built_at: datetime | None = None
    uploaded_by: str | None = None
    uploaded_by_name: str | None = None
    # Имя токена-устройства (запись входа локальной Студии), по которому выгружено.
    client_name: str | None = None


@dataclass(frozen=True)
class PdfUploadLimits:
    max_bytes: int = 104_857_600
    keep_per_document: int = 5


def is_safe_doc_id(doc_id: str) -> bool:
    return _DOC_ID_RE.fullmatch(doc_id) is not None


def artifact_key(project_id: UUID, doc_id: str, artifact_id: UUID) -> str:
    """`artifacts/<project_id>/uploads/<doc_id>/<artifact_id>.pdf`: под префиксом, который учитывает квота проекта."""
    if not is_safe_doc_id(doc_id):
        msg = "doc_id содержит недопустимые символы"
        raise ValueError(msg)
    return f"artifacts/{project_id}/uploads/{doc_id}/{artifact_id}.pdf"


def safe_file_name(doc_id: str, name: str | None) -> str:
    """Имя для скачивания: из заголовка клиента, очищенное от путей и управляющих символов; без него `<doc_id>.pdf`."""
    base = re.sub(r"[^\w.\- ]", "_", (name or "").strip(), flags=re.UNICODE).strip(" .")[:120]
    base = base.removesuffix(".pdf").removesuffix(".PDF").strip(" .") or doc_id
    return f"{base}.pdf"
