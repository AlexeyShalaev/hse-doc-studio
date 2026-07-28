from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import PackSubmissionRecord
from hse_doc_studio.core.repositories import (
    IPackSubmissionRepository,
    IProjectIndexRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class ListSubmissionsInput:
    project_id: UUID


@dataclass
class SubmissionListItem:
    record: PackSubmissionRecord
    size_bytes: int | None
    # Localized profile name resolved from the template version (None if the
    # profile no longer exists in the pinned version).
    profile_name: dict[str, str] | None


@dataclass
class ListSubmissionsOutput:
    items: list[SubmissionListItem]


def _safe_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


class ListSubmissionsUC:
    """Lists past submission packs for a project, newest first.

    Records live as <project>/.hse-studio/submissions/<uuid>.json; the actual
    archive sits at record.output_path. We stat each archive to surface its size
    (None when the file has since been moved or deleted) and resolve the
    profile's localized name from the pinned template version, so the UI can
    render a rich journal without extra round-trips.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        submission_repo: IPackSubmissionRepository,
        template_repo: ITemplateRepository,
    ) -> None:
        self._submission_repo = submission_repo
        self._template_repo = template_repo
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: ListSubmissionsInput) -> ListSubmissionsOutput:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        version = self._template_repo.get_version(
            project.lock.pack_id,
            project.lock.template_id,
            project.lock.version,
        )
        profile_names: dict[str, dict[str, str]] = {}
        if version is not None:
            profile_names = {p.id: p.name for p in version.pack_submission.profiles}

        # list_for_project sorts oldest-first; the journal shows latest at top.
        records = self._submission_repo.list_for_project(project.folder)
        records.reverse()

        items = [
            SubmissionListItem(
                record=record,
                size_bytes=_safe_size(record.output_path),
                profile_name=profile_names.get(record.profile_id),
            )
            for record in records
        ]
        return ListSubmissionsOutput(items=items)
