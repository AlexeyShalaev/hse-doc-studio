from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.core.repositories import (
    IFileRepository,
    IProjectIndexRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.vcs.protocols import (
    IVcsEditThrottle,
    IVcsFolderLocks,
    IVcsService,
)
from hse_doc_studio.use_cases.files._template_guard import (
    is_protected_path,
    template_protected_paths,
)
from hse_doc_studio.use_cases.files._vcs_edit import maybe_edit_commit
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class MoveFileInput:
    project_id: UUID
    src: str
    dst: str


class MoveFileUC:
    """Renames/moves a file or directory within a project."""

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        file_repo: IFileRepository,
        template_repo: ITemplateRepository,
        vcs_service: IVcsService,
        vcs_locks: IVcsFolderLocks,
        vcs_throttle: IVcsEditThrottle,
    ) -> None:
        self._file_repo = file_repo
        self._template_repo = template_repo
        self._vcs = vcs_service
        self._vcs_locks = vcs_locks
        self._vcs_throttle = vcs_throttle
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: MoveFileInput) -> None:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        protected = template_protected_paths(self._template_repo, project)
        if is_protected_path(inp.src, protected):
            raise PermissionError(
                f"«{inp.src}» is part of the template and is protected from renaming/moving."
                if current_interface_language() is Lang.en
                else f"«{inp.src}» входит в шаблон и защищён от переименования/перемещения."
            )

        self._file_repo.move(project.folder, inp.src, inp.dst)
        logger.debug(
            "file moved via use case",
            project_id=str(inp.project_id),
            src=inp.src,
            dst=inp.dst,
        )
        await maybe_edit_commit(
            self._vcs, self._vcs_locks, self._vcs_throttle, project, f"Переименование: {inp.src} → {inp.dst}"
        )
