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
class GetCompileInput:
    project_id: UUID
    compile_id: UUID


class GetCompileUC:
    """Reads a single persisted compile record by id.

    The signature editor and the build history both need to know the outcome
    of a finished build *after* the live SSE stream has gone — that data lives
    only in the per-project JSON record, which is keyed by project folder, so we
    resolve the folder from project_id via the project index first.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        compile_repo: JsonCompileRepository,
    ) -> None:
        self._project_repo = project_repo
        self._project_index_repo = project_index_repo
        self._compile_repo = compile_repo

    def execute(self, inp: GetCompileInput) -> CompileRecord | None:
        project_folder = self._find_folder(inp.project_id)
        if project_folder is None:
            return None
        return self._compile_repo.get_for_project(project_folder, inp.compile_id)

    def _find_folder(self, project_id: UUID) -> Path | None:
        for folder in self._project_index_repo.list_known():
            try:
                project = self._project_repo.get(folder)
                if project is not None and project.id == project_id:
                    return folder
            except Exception as exc:
                logger.warning("get_compile: error loading project", folder=str(folder), exc=str(exc))
        return None
