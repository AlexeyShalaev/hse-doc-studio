from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import ChangeLogEntry
from hse_doc_studio.core.enums import ChangeLogKind, VcsRestoreMode
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IChangeLogRepository,
    IProjectIndexRepository,
    IProjectRepository,
)
from hse_doc_studio.core.vcs.entities import VcsRestoreResult, VcsSettings
from hse_doc_studio.core.vcs.errors import VcsUnavailableError
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks, IVcsService
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class RestoreVcsInput:
    project_id: UUID
    commit_id: str
    paths: list[str] | None = None
    mode: VcsRestoreMode = VcsRestoreMode.snapshot
    confirm: bool = False  # required for the destructive hard mode


@dataclass
class RestoreVcsOutput:
    result: VcsRestoreResult


class RestoreVcsUC:
    """Roll the working tree back to a past commit. Safe by default: the current
    state is auto-snapshotted, then a new `restore` commit records the rollback
    (HEAD/history never rewritten, fully undoable). `hard` mode is destructive and
    must be explicitly confirmed."""

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        vcs_service: IVcsService,
        changelog_repo: IChangeLogRepository,
        locks: IVcsFolderLocks,
    ) -> None:
        self._vcs = vcs_service
        self._changelog_repo = changelog_repo
        self._locks = locks
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: RestoreVcsInput) -> RestoreVcsOutput:
        if inp.mode == VcsRestoreMode.hard and not inp.confirm:
            raise ValueError(
                localized_error("Жёсткий откат требует confirm=true", "Hard restore requires confirm=true")
            )

        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        if not self._vcs.is_available(project):
            raise VcsUnavailableError(
                localized_error(
                    f"папка проекта недоступна: {project.folder}",
                    f"project folder not accessible: {project.folder}",
                )
            )
        settings = VcsSettings.from_meta(project.meta)

        async with self._locks.for_folder(project.folder):
            result = await asyncio.to_thread(
                lambda: self._vcs.restore(
                    project,
                    commit_id=inp.commit_id,
                    paths=inp.paths,
                    mode=inp.mode,
                    include_pdf=settings.track_pdf,
                )
            )

        self._changelog_repo.append(
            project.folder,
            ChangeLogEntry(
                id=uuid.uuid4(),
                at=datetime.now(tz=timezone.utc),
                kind=ChangeLogKind.manual_note,
                doc_id=None,
                summary=f"Откат к версии {result.restored_from[:7]}",
                note=None,
            ),
        )
        logger.info(
            "vcs restored",
            project_id=str(inp.project_id),
            to=result.restored_from[:7],
            mode=str(inp.mode),
        )
        return RestoreVcsOutput(result=result)
