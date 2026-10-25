from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.project_access import ProjectAccess, evaluate_project_access
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository, ITemplateRepository
from hse_doc_studio.core.template_update.protocols import IUpdateJournalRepository
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC


class ProjectAccessService:
    """Доступ к проекту в этой Студии (core.project_access) по его текущему состоянию."""

    def __init__(self, template_repo: ITemplateRepository, journal_repo: IUpdateJournalRepository) -> None:
        self._template_repo = template_repo
        self._journals = journal_repo

    def evaluate(self, project: Project) -> ProjectAccess:
        lock = project.lock
        return evaluate_project_access(
            project,
            template_available=self._template_repo.get_version(lock.pack_id, lock.template_id, lock.version)
            is not None,
            update_in_progress=self._journals.get(project.folder) is not None,
        )


@dataclass
class GetProjectAccessInput:
    project_id: UUID


@dataclass
class GetProjectAccessOutput:
    project: Project
    access: ProjectAccess


class GetProjectAccessUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        access_service: ProjectAccessService,
    ) -> None:
        self._get_uc = GetProjectUC(project_repo, project_index_repo)
        self._access = access_service

    async def execute(self, inp: GetProjectAccessInput) -> GetProjectAccessOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        return GetProjectAccessOutput(project=project, access=self._access.evaluate(project))
