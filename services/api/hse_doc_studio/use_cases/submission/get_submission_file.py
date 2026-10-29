from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IPackSubmissionRepository,
    IProjectIndexRepository,
    IProjectRepository,
)
from hse_doc_studio.core.submission_archive import (
    DisabledSubmissionArchive,
    ISubmissionArchive,
    ISubmissionAudit,
    NoSubmissionAudit,
)
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC


@dataclass
class GetSubmissionFileInput:
    project_id: UUID
    submission_id: UUID


@dataclass
class GetSubmissionFileOutput:
    """Либо файл на диске (локальный режим), либо ссылка на хранилище, либо поток из него."""

    download_name: str
    path: Path | None = None
    redirect_url: str | None = None
    stream: AsyncIterator[bytes] | None = None


class GetSubmissionFileUC:
    """Resolves the archive of a previously-created submission so the API can send it back as a download.

    Raises NotFoundError (mapped to 404 by the router) when either the journal
    record or its archive is missing. Locally the archive lives under the project
    tree at record.output_path; on the server it lives in the object store under
    record.artifact_key and every download is written to the audit log.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        submission_repo: IPackSubmissionRepository,
        archive: ISubmissionArchive | None = None,
        audit: ISubmissionAudit | None = None,
    ) -> None:
        self._submission_repo = submission_repo
        self._archive = archive or DisabledSubmissionArchive()
        self._audit = audit or NoSubmissionAudit()
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: GetSubmissionFileInput) -> GetSubmissionFileOutput:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        record = await self._submission_repo.get(project.folder, inp.submission_id)
        if record is None:
            raise NotFoundError(
                localized_error(
                    f"Пакет сдачи не найден: {inp.submission_id}", f"Submission not found: {inp.submission_id}"
                )
            )

        name = record.output_path.name
        if record.artifact_key is not None and self._archive.enabled:
            return await self._from_archive(inp, record.artifact_key, name)

        if not record.output_path.exists():
            raise NotFoundError(
                localized_error(
                    f"Архив пакета сдачи не найден по пути {record.output_path}",
                    f"Submission archive not found at {record.output_path}",
                )
            )
        await self._audit.downloaded(current_actor(), inp.project_id, inp.submission_id, via="volume")
        return GetSubmissionFileOutput(download_name=name, path=record.output_path)

    async def _from_archive(self, inp: GetSubmissionFileInput, key: str, name: str) -> GetSubmissionFileOutput:
        try:
            link = await self._archive.link(key)
            if link is None and await self._archive.size(key) is None:
                raise FileNotFoundError(key)
        except FileNotFoundError:
            raise NotFoundError(
                localized_error("Архив пакета сдачи не найден в хранилище", "Submission archive not found in storage")
            ) from None
        # Аудит до выдачи ссылки: выданная ссылка уже даёт скачать, откатить это нельзя.
        await self._audit.downloaded(
            current_actor(), inp.project_id, inp.submission_id, via="link" if link is not None else "stream"
        )
        if link is not None:
            return GetSubmissionFileOutput(download_name=name, redirect_url=link.url)
        return GetSubmissionFileOutput(download_name=name, stream=self._archive.stream(key))
