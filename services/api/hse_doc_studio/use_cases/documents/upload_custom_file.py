from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
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
    ISignatureRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.value_objects import CustomFileOverride, SignaturesState
from hse_doc_studio.core.vcs.protocols import IVcsEditThrottle, IVcsFolderLocks, IVcsService
from hse_doc_studio.infra.office.convert_manager import CONVERTIBLE_OFFICE_EXTS, OfficeConvertManager
from hse_doc_studio.use_cases.files._vcs_edit import maybe_edit_commit
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class UploadCustomFileInput:
    project_id: UUID
    doc_id: str
    filename: str
    content: bytes


@dataclass
class UploadCustomFileOutput:
    document: Document
    preview_generated: bool


class UploadCustomFileUC:
    """Replaces a document's pack-generated output with a user-uploaded file.

    Stores the file under the document's own `_custom/` subdirectory (team-
    aware via `custom_upload_dir`), disables (never deletes) any existing
    signature placements for this doc — template-authored coordinates almost
    certainly don't fit an arbitrary layout, so re-review is required rather
    than silently keeping wrong coordinates — and best-effort generates a PDF
    preview for convertible office formats.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        file_repo: IFileRepository,
        signature_repo: ISignatureRepository,
        office_manager: OfficeConvertManager,
        vcs_service: IVcsService,
        vcs_locks: IVcsFolderLocks,
        vcs_throttle: IVcsEditThrottle,
    ) -> None:
        self._template_repo = template_repo
        self._file_repo = file_repo
        self._signature_repo = signature_repo
        self._office_manager = office_manager
        self._vcs = vcs_service
        self._vcs_locks = vcs_locks
        self._vcs_throttle = vcs_throttle
        self._template_service = ProjectTemplateService()
        self._get_uc = GetProjectUC(project_repo, project_index_repo)
        self._project_repo = project_repo

    async def execute(self, inp: UploadCustomFileInput) -> UploadCustomFileOutput:
        if not inp.content:
            raise ValueError(localized_error("Пустой загружаемый файл", "Empty file upload"))
        safe_name = Path(inp.filename).name
        if not safe_name:
            raise ValueError(localized_error("Некорректное имя файла", "Invalid filename"))

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

        version = self._template_repo.get_version(
            project.lock.pack_id,
            project.lock.template_id,
            project.lock.version,
        )
        if version is None:
            raise NotFoundError(
                localized_error(
                    f"Версия шаблона для проекта {inp.project_id} не найдена",
                    f"Template version not found for project {inp.project_id}",
                )
            )

        upload_dir = self._template_service.custom_upload_dir(project, doc, version)
        stored_path = f"{upload_dir}/{safe_name}"

        if doc.custom_file is not None and doc.custom_file.stored_path != stored_path:
            self._delete_stored_file(project.folder, doc.custom_file.stored_path)

        self._file_repo.write(project.folder, stored_path, inp.content)

        ext = Path(safe_name).suffix.lower()
        custom_file = CustomFileOverride(
            original_filename=safe_name,
            stored_path=stored_path,
            ext=ext,
            uploaded_at=datetime.now(tz=timezone.utc).isoformat(),
            convert_to_pdf_at_package=None,
        )

        doc_index = project.documents.index(doc)
        updated_doc = replace(
            doc,
            custom_file=custom_file,
            status=DocumentStatus.draft,
            last_compile_id=None,
        )
        project.documents[doc_index] = updated_doc

        self._disable_placements(project.folder, updated_doc.id)

        self._project_repo.save(project)

        preview_generated = False
        if ext != ".pdf" and ext in CONVERTIBLE_OFFICE_EXTS:
            preview_generated = await self._generate_preview(project.folder, stored_path)

        logger.info(
            "custom file uploaded",
            project_id=str(inp.project_id),
            doc_id=inp.doc_id,
            stored_path=stored_path,
            preview_generated=preview_generated,
        )
        await maybe_edit_commit(
            self._vcs,
            self._vcs_locks,
            self._vcs_throttle,
            project,
            f"Загрузка пользовательского файла: {inp.doc_id} ({safe_name})",
        )

        return UploadCustomFileOutput(document=updated_doc, preview_generated=preview_generated)

    def _delete_stored_file(self, project_folder: Path, stored_path: str) -> None:
        for candidate in (stored_path, str(Path(stored_path).with_suffix(".pdf")).replace("\\", "/")):
            try:
                if self._file_repo.exists(project_folder, candidate):
                    self._file_repo.delete(project_folder, candidate)
            except OSError as exc:
                logger.warning("upload_custom_file: failed to delete stale file", path=candidate, exc=str(exc))

    def _disable_placements(self, project_folder: Path, doc_id: str) -> None:
        state = self._signature_repo.get_state(project_folder)
        doc_placements = state.placements.get(doc_id)
        if not doc_placements:
            return
        updated = {slot_id: replace(p, enabled=False) for slot_id, p in doc_placements.items()}
        new_placements = {**state.placements, doc_id: updated}
        self._signature_repo.save_state(project_folder, SignaturesState(slots=state.slots, placements=new_placements))

    async def _generate_preview(self, project_folder: Path, stored_path: str) -> bool:
        src_abs = project_folder / stored_path
        pdf_abs = src_abs.with_suffix(".pdf")
        try:
            pdf_bytes = await self._office_manager.convert_to_pdf(src_abs)
        except Exception as exc:  # noqa: BLE001 — preview is best-effort
            logger.warning("upload_custom_file: preview conversion failed", path=stored_path, exc=str(exc))
            return False
        if pdf_bytes is None:
            return False
        try:
            pdf_abs.write_bytes(pdf_bytes)
        except OSError as exc:
            logger.warning("upload_custom_file: preview write failed", path=str(pdf_abs), exc=str(exc))
            return False
        return True
