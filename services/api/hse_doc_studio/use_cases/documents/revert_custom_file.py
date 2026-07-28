from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import Document
from hse_doc_studio.core.enums import DocumentStatus
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IFileRepository,
    IProjectIndexRepository,
    IProjectRepository,
)
from hse_doc_studio.core.vcs.protocols import IVcsEditThrottle, IVcsFolderLocks, IVcsService
from hse_doc_studio.use_cases.files._vcs_edit import maybe_edit_commit
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class RevertCustomFileInput:
    project_id: UUID
    doc_id: str
    delete_uploaded_file: bool = False


@dataclass
class RevertCustomFileOutput:
    document: Document


class RevertCustomFileUC:
    """Clears a document's custom-file override, falling back to `chosen_variant`.

    By default the stored upload is kept on disk (cheap undo); the caller may
    request `delete_uploaded_file=True` to also remove it (and its sibling PDF
    preview, if any).
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        file_repo: IFileRepository,
        vcs_service: IVcsService,
        vcs_locks: IVcsFolderLocks,
        vcs_throttle: IVcsEditThrottle,
    ) -> None:
        self._file_repo = file_repo
        self._vcs = vcs_service
        self._vcs_locks = vcs_locks
        self._vcs_throttle = vcs_throttle
        self._get_uc = GetProjectUC(project_repo, project_index_repo)
        self._project_repo = project_repo

    async def execute(self, inp: RevertCustomFileInput) -> RevertCustomFileOutput:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        doc = next((d for d in project.documents if d.id == inp.doc_id), None)
        if doc is None:
            raise NotFoundError(
                localized_error(
                    f"Документ {inp.doc_id!r} не найден в проекте {inp.project_id}",
                    f"Document {inp.doc_id!r} not found in project {inp.project_id}",
                )
            )
        if doc.custom_file is None:
            raise ValueError(
                localized_error(
                    f"У документа {inp.doc_id!r} нет пользовательского файла для отката",
                    f"Document {inp.doc_id!r} has no custom file to revert",
                )
            )

        stored_path = doc.custom_file.stored_path
        doc_index = project.documents.index(doc)
        updated_doc = replace(
            doc,
            custom_file=None,
            status=DocumentStatus.draft,
            last_compile_id=None,
        )
        project.documents[doc_index] = updated_doc
        self._project_repo.save(project)

        if inp.delete_uploaded_file:
            self._delete_stored_file(project.folder, stored_path)

        logger.info(
            "custom file reverted",
            project_id=str(inp.project_id),
            doc_id=inp.doc_id,
            deleted=inp.delete_uploaded_file,
        )
        await maybe_edit_commit(
            self._vcs,
            self._vcs_locks,
            self._vcs_throttle,
            project,
            f"Возврат к шаблону: {inp.doc_id}",
        )

        return RevertCustomFileOutput(document=updated_doc)

    def _delete_stored_file(self, project_folder: Path, stored_path: str) -> None:
        for candidate in (stored_path, str(Path(stored_path).with_suffix(".pdf")).replace("\\", "/")):
            try:
                if self._file_repo.exists(project_folder, candidate):
                    self._file_repo.delete(project_folder, candidate)
            except OSError as exc:
                logger.warning("revert_custom_file: failed to delete file", path=candidate, exc=str(exc))
