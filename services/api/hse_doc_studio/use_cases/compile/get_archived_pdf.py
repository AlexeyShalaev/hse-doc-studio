from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.jobs.artifacts import IArtifactStore
from hse_doc_studio.core.projects.locator import IProjectLocator

logger = structlog.get_logger()


@dataclass
class GetArchivedPdfInput:
    project_id: UUID
    doc_id: str
    compile_id: UUID


@dataclass
class GetArchivedPdfOutput:
    """Либо байты, либо ссылка на хранилище (Range для pdf.js читает уже оно)."""

    content: bytes | None = None
    redirect_url: str | None = None


class GetArchivedPdfUC:
    """Serves a previously-archived compiled PDF (for the visual diff feature)."""

    def __init__(
        self,
        locator: IProjectLocator,
        artifacts: IArtifactStore,
    ) -> None:
        self._locator = locator
        self._artifacts = artifacts

    async def execute(self, inp: GetArchivedPdfInput) -> GetArchivedPdfOutput:
        folder = await self._locator.folder_of(inp.project_id)
        if folder is None:
            raise NotFoundError(
                localized_error(f"Проект {inp.project_id} не найден", f"Project not found: {inp.project_id}")
            )
        try:
            link = await self._artifacts.archived_pdf_link(inp.project_id, inp.doc_id, inp.compile_id)
            if link is not None:
                return GetArchivedPdfOutput(redirect_url=link.url)
            content = await self._artifacts.read_archived_pdf(inp.project_id, folder, inp.doc_id, inp.compile_id)
        except FileNotFoundError:
            raise NotFoundError(
                localized_error("Для этой сборки нет архивного PDF", "No archived PDF for this build")
            ) from None
        return GetArchivedPdfOutput(content=content)
