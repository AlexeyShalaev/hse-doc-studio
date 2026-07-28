from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import ChangeLogEntry
from hse_doc_studio.core.enums import ChangeLogKind, VcsCommitKind
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IChangeLogRepository,
    IProjectIndexRepository,
    IProjectRepository,
)
from hse_doc_studio.core.vcs.constants import DEFAULT_VCS_EXCLUDE
from hse_doc_studio.core.vcs.entities import VcsCommit, VcsSettings
from hse_doc_studio.core.vcs.errors import VcsUnavailableError
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks, IVcsService
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class CreateVcsSnapshotInput:
    project_id: UUID
    message: str
    doc_id: str | None = None


@dataclass
class CreateVcsSnapshotOutput:
    commit: VcsCommit | None  # None when there was nothing to commit


class CreateVcsSnapshotUC:
    """Manual "Save snapshot": a user-labelled commit. Mirrors a ChangeLog
    manual_note so the semantic journal records the milestone too."""

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

    async def execute(self, inp: CreateVcsSnapshotInput) -> CreateVcsSnapshotOutput:
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
            if not self._vcs.is_initialized(project):
                await asyncio.to_thread(self._vcs.init, project, list(DEFAULT_VCS_EXCLUDE))
            commit = await asyncio.to_thread(
                lambda: self._vcs.commit(
                    project,
                    message=inp.message,
                    kind=VcsCommitKind.manual,
                    include_pdf=settings.track_pdf,
                )
            )

        if commit is not None:
            self._changelog_repo.append(
                project.folder,
                ChangeLogEntry(
                    id=uuid.uuid4(),
                    at=datetime.now(tz=timezone.utc),
                    kind=ChangeLogKind.manual_note,
                    doc_id=inp.doc_id,
                    summary=inp.message,
                    note=None,
                ),
            )
            logger.info("vcs snapshot created", project_id=str(inp.project_id), commit=commit.short_id)
        return CreateVcsSnapshotOutput(commit=commit)
