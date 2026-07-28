from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import CompileRecord
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository
from hse_doc_studio.infra.persistence.compile import JsonCompileRepository

logger = structlog.get_logger()


@dataclass
class ListCompilesInput:
    project_id: UUID
    doc_id: str


class ListCompilesUC:
    """Lists a document's compile history (oldest-first) from the project store."""

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        compile_repo: JsonCompileRepository,
    ) -> None:
        self._project_repo = project_repo
        self._project_index_repo = project_index_repo
        self._compile_repo = compile_repo

    def execute(self, inp: ListCompilesInput) -> list[CompileRecord]:
        project_folder = self._find_folder(inp.project_id)
        if project_folder is None:
            return []
        return self._compile_repo.list_for_document(project_folder, inp.doc_id)

    def _find_folder(self, project_id: UUID) -> Path | None:
        for folder in self._project_index_repo.list_known():
            try:
                project = self._project_repo.get(folder)
                if project is not None and project.id == project_id:
                    return folder
            except Exception as exc:
                logger.warning("list_compiles: error loading project", folder=str(folder), exc=str(exc))
        return None
