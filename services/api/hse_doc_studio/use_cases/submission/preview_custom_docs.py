from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import SubmissionProfileService
from hse_doc_studio.core.team import author_by_slug
from hse_doc_studio.infra.office.convert_manager import CONVERTIBLE_OFFICE_EXTS
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class PreviewSubmissionCustomDocsInput:
    project_id: UUID
    profile_id: str
    author_slug: str | None = None


@dataclass(frozen=True)
class CustomDocPreviewItem:
    doc_id: str
    doc_name: dict[str, str]
    original_filename: str
    ext: str
    convertible: bool
    default_decision: bool | None


@dataclass
class PreviewSubmissionCustomDocsOutput:
    items: list[CustomDocPreviewItem]


class PreviewSubmissionCustomDocsUC:
    """Preflight before a real package build: which custom-file documents (if
    any) in this profile's item list need a convert-to-PDF decision.

    Documents whose custom_file is already a PDF need no decision and are
    omitted. An empty result (the common case) means the frontend has nothing
    to ask the user — this must stay cheap and fast.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        submission_profile_service: SubmissionProfileService,
    ) -> None:
        self._template_repo = template_repo
        self._submission_profile_service = submission_profile_service
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: PreviewSubmissionCustomDocsInput) -> PreviewSubmissionCustomDocsOutput:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        version = self._template_repo.get_version(
            project.lock.pack_id,
            project.lock.template_id,
            project.lock.version,
        )
        if version is None:
            version_ref = f"{project.lock.pack_id}/{project.lock.template_id}/{project.lock.version}"
            raise NotFoundError(
                localized_error(
                    f"Версия шаблона не найдена: {version_ref}", f"Template version not found: {version_ref}"
                )
            )

        profile = self._submission_profile_service.get_profile(version, inp.profile_id)
        if profile is None:
            raise NotFoundError(
                localized_error(
                    f"Профиль сдачи {inp.profile_id!r} не найден", f"Submission profile {inp.profile_id!r} not found"
                )
            )

        team = str(project.staffing) == "team"
        author = author_by_slug(project, inp.author_slug) if team else None
        if team and author is None:
            raise ValueError(
                localized_error(
                    "Командный проект: укажите существующего автора (author_slug) для пакета сдачи",
                    "Team project: specify an existing author (author_slug) for the submission package",
                )
            )

        instances = self._submission_profile_service.resolve_profile_doc_instances(
            profile=profile,
            project=project,
            version=version,
            author_slug=inp.author_slug if team else None,
        )

        doc_def_by_def_id = {d.id: d for d in version.documents}

        items: list[CustomDocPreviewItem] = []
        for doc in instances:
            if doc.custom_file is None:
                continue
            if doc.custom_file.ext == ".pdf":
                continue
            doc_def = doc_def_by_def_id.get(doc.def_id)
            doc_name = dict(doc_def.name) if doc_def is not None else {"ru": doc.id}
            items.append(
                CustomDocPreviewItem(
                    doc_id=doc.id,
                    doc_name=doc_name,
                    original_filename=doc.custom_file.original_filename,
                    ext=doc.custom_file.ext,
                    convertible=doc.custom_file.ext in CONVERTIBLE_OFFICE_EXTS,
                    default_decision=doc.custom_file.convert_to_pdf_at_package,
                )
            )

        return PreviewSubmissionCustomDocsOutput(items=items)
