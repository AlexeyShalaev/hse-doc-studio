"""Порт публикации и архива PDF сборки (только compile, шире порт не растёт)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.storage.models import PresignedUrl


@dataclass(frozen=True)
class PublishPdfRequest:
    workspace: Path
    doc_id: str
    job_id: UUID
    source_file: str
    project_id: UUID | None = None
    """Ключ проекта для серверного хранилища; локальная реализация его не использует."""


@dataclass(frozen=True)
class PublishPdfOutcome:
    """`replaced=False`: PDF рядом с исходником не заменён, свежая копия осталась в `.build`."""

    replaced: bool
    final_name: str


class IArtifactStore(Protocol):
    async def publish_pdf(self, req: PublishPdfRequest) -> PublishPdfOutcome:
        """Переносит собранный PDF из `.build/<doc_id>/` к исходнику."""
        ...

    async def archive_pdf(self, project_id: UUID, workspace: Path, doc_id: str, job_id: UUID, source_file: str) -> None:
        """Кладёт свежий PDF в архив документа, оставляя последние несколько."""
        ...

    async def read_archived_pdf(self, project_id: UUID, workspace: Path, doc_id: str, job_id: UUID) -> bytes:
        """Отдаёт архивный PDF сборки. `FileNotFoundError`, если архива нет."""
        ...

    async def archived_pdf_link(self, project_id: UUID, doc_id: str, job_id: UUID) -> PresignedUrl | None:
        """Короткоживущая ссылка на архивный PDF с Range; None, если хранилище ссылок не выдаёт.
        `FileNotFoundError`, если архива нет."""
        ...
