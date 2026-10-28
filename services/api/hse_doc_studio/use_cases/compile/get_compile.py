from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import CompileRecord
from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.core.repositories import ICompileRepository

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
        locator: IProjectLocator,
        compile_repo: ICompileRepository,
    ) -> None:
        self._locator = locator
        self._compile_repo = compile_repo

    async def execute(self, inp: GetCompileInput) -> CompileRecord | None:
        project_folder = await self._locator.folder_of(inp.project_id)
        if project_folder is None:
            return None
        return self._compile_repo.get_for_project(project_folder, inp.compile_id)
