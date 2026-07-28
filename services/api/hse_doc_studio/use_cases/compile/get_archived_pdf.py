from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
)
from hse_doc_studio.infra.compile.pdf_archive import archived_pdf_path

logger = structlog.get_logger()


@dataclass
class GetArchivedPdfInput:
    project_id: UUID
    doc_id: str
    compile_id: UUID


@dataclass
class GetArchivedPdfOutput:
    content: bytes


class GetArchivedPdfUC:
    """Serves a previously-archived compiled PDF (for the visual diff feature)."""

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
    ) -> None:
        self._project_repo = project_repo
        self._project_index_repo = project_index_repo

    def execute(self, inp: GetArchivedPdfInput) -> GetArchivedPdfOutput:
        folder = self._find_folder(inp.project_id)
        if folder is None:
            raise NotFoundError(
                localized_error(f"Проект {inp.project_id} не найден", f"Project not found: {inp.project_id}")
            )
        path = archived_pdf_path(folder, inp.doc_id, inp.compile_id)
        if not path.exists():
            raise NotFoundError(localized_error("Для этой сборки нет архивного PDF", "No archived PDF for this build"))
        return GetArchivedPdfOutput(content=path.read_bytes())

    def _find_folder(self, project_id: UUID) -> Path | None:
        for folder in self._project_index_repo.list_known():
            try:
                project = self._project_repo.get(folder)
                if project is not None and project.id == project_id:
                    return folder
            except Exception as exc:
                logger.warning(
                    "get_archived_pdf: project load error",
                    folder=str(folder),
                    exc=str(exc),
                )
        return None
