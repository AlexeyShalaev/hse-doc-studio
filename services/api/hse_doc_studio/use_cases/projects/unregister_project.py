from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode
from hse_doc_studio.core.git_sync.protocols import IGitOperationRegistry, IGitRemoteRegistry
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
)
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class UnregisterProjectInput:
    project_id: UUID


class UnregisterProjectUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        git_operations: IGitOperationRegistry,
        git_remotes: IGitRemoteRegistry,
    ) -> None:
        self._project_repo = project_repo
        self._project_index_repo = project_index_repo
        self._git_operations = git_operations
        self._git_remotes = git_remotes
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: UnregisterProjectInput) -> None:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        # Синхронизация, которая ещё идёт, потеряла бы проект из-под ног: сначала её отмена или конец.
        if self._git_operations.is_busy(project.folder):
            current = self._git_operations.current_for(project.id)
            raise git_error(GitErrorCode.sync_busy, operation_id=current.id if current else None)

        self._project_index_repo.unregister(project.folder)
        self._git_remotes.remove(project.folder)
        logger.info(
            "project unregistered",
            project_id=str(inp.project_id),
            folder=str(project.folder),
        )
