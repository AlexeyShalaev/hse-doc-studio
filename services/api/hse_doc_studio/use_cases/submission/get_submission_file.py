from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IPackSubmissionRepository,
    IProjectIndexRepository,
    IProjectRepository,
)
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC


@dataclass
class GetSubmissionFileInput:
    project_id: UUID
    submission_id: UUID


@dataclass
class GetSubmissionFileOutput:
    path: Path
    download_name: str


class GetSubmissionFileUC:
    """Resolves the on-disk ZIP for a previously-created submission so the API
    can stream it back as a download.

    Raises NotFoundError (mapped to 404 by the router) when either the journal
    record or its archive is missing — the ZIP lives under the project tree at
    record.output_path and may have been moved or cleaned up out of band.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        submission_repo: IPackSubmissionRepository,
    ) -> None:
        self._submission_repo = submission_repo
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: GetSubmissionFileInput) -> GetSubmissionFileOutput:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        record = self._submission_repo.get(project.folder, inp.submission_id)
        if record is None:
            raise NotFoundError(
                localized_error(
                    f"Пакет сдачи не найден: {inp.submission_id}", f"Submission not found: {inp.submission_id}"
                )
            )

        if not record.output_path.exists():
            raise NotFoundError(
                localized_error(
                    f"Архив пакета сдачи не найден по пути {record.output_path}",
                    f"Submission archive not found at {record.output_path}",
                )
            )

        return GetSubmissionFileOutput(
            path=record.output_path,
            download_name=record.output_path.name,
        )
