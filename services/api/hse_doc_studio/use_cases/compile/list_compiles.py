from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import CompileRecord
from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.core.repositories import ICompileRepository

logger = structlog.get_logger()


@dataclass
class ListCompilesInput:
    project_id: UUID
    doc_id: str


class ListCompilesUC:
    """Lists a document's compile history (oldest-first) from the project store."""

    def __init__(
        self,
        locator: IProjectLocator,
        compile_repo: ICompileRepository,
    ) -> None:
        self._locator = locator
        self._compile_repo = compile_repo

    async def execute(self, inp: ListCompilesInput) -> list[CompileRecord]:
        project_folder = await self._locator.folder_of(inp.project_id)
        if project_folder is None:
            return []
        return self._compile_repo.list_for_document(project_folder, inp.doc_id)
