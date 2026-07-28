from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import ChangeLogEntry
from hse_doc_studio.core.enums import ChangeLogKind
from hse_doc_studio.core.repositories import (
    IChangeLogRepository,
    IProjectIndexRepository,
    IProjectRepository,
)
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class AddChangelogEntryInput:
    project_id: UUID
    summary: str
    doc_id: str | None = None
    kind: ChangeLogKind = ChangeLogKind.manual_note
    note: str | None = None


@dataclass
class AddChangelogEntryOutput:
    entry: ChangeLogEntry


class AddChangelogEntryUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        changelog_repo: IChangeLogRepository,
    ) -> None:
        self._changelog_repo = changelog_repo
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: AddChangelogEntryInput) -> AddChangelogEntryOutput:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        entry = ChangeLogEntry(
            id=uuid.uuid4(),
            at=datetime.now(tz=timezone.utc),
            kind=inp.kind,
            doc_id=inp.doc_id,
            summary=inp.summary,
            note=inp.note,
        )
        self._changelog_repo.append(project.folder, entry)

        logger.info(
            "changelog entry added",
            project_id=str(inp.project_id),
            kind=str(inp.kind),
        )
        return AddChangelogEntryOutput(entry=entry)
