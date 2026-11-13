"""Порт публикации и архива PDF сборки (только compile, шире порт не растёт)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.storage.models import PresignedUrl


class PositionsSource(StrEnum):
    """Откуда файл позиций якорей (`<stem>.hsepos`) в каталоге сборки при публикации PDF (signing-route.md, 15.17.6)."""

    # Сборка шла здесь же (docker, kubernetes, встроенный раннер): свежесть по `.fls` последнего прохода TeX.
    tex = "tex"
    # Файл выгрузил удалённый раннер вместе с PDF этой задачи (возможность `build_anchors`), свежесть проверил он.
    runner = "runner"
    # Раннер файла не выгрузил (прежняя версия, нет `build_anchors`, шаблон без якорей): всё, что лежит в каталоге
    # сборки, от прошлых сборок, и якоря неизвестны.
    absent = "absent"


@dataclass(frozen=True)
class PublishPdfRequest:
    workspace: Path
    doc_id: str
    job_id: UUID
    source_file: str
    project_id: UUID | None = None
    """Ключ проекта для серверного хранилища; локальная реализация его не использует."""
    positions: PositionsSource = PositionsSource.tex


@dataclass(frozen=True)
class PublishPdfOutcome:
    """`replaced=False`: PDF рядом с исходником не заменён, свежая копия осталась в `.build`."""

    replaced: bool
    final_name: str


@dataclass(frozen=True)
class PdfFingerprint:
    """Размер и SHA-256 готового PDF: по ним облако и Студия сверяют, одна ли у них сборка."""

    size: int
    sha256: str


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

    async def fingerprint_pdf(self, workspace: Path, doc_id: str, source_file: str) -> PdfFingerprint | None:
        """Отпечаток свежего PDF документа (рядом с исходником или в `.build`); None, если файла нет."""
        ...
