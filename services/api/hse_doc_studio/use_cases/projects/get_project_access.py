from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.project_access import ProjectAccess, StalePacks, evaluate_project_access
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository, ITemplateRepository
from hse_doc_studio.core.template_packs import ITemplatePacksSource, TemplateKey
from hse_doc_studio.core.template_update.protocols import IUpdateJournalRepository
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC


class ProjectAccessService:
    """Доступ к проекту в этой Студии (core.project_access) по его текущему состоянию."""

    def __init__(
        self,
        template_repo: ITemplateRepository,
        journal_repo: IUpdateJournalRepository,
        packs: ITemplatePacksSource | None = None,
    ) -> None:
        self._template_repo = template_repo
        self._journals = journal_repo
        self._packs = packs

    def evaluate(self, project: Project) -> ProjectAccess:
        lock = project.lock
        available = self._template_repo.get_version(lock.pack_id, lock.template_id, lock.version) is not None
        return evaluate_project_access(
            project,
            template_available=available,
            update_in_progress=self._journals.get(project.folder) is not None,
            stale_packs=None
            if available
            else self._stale_packs(TemplateKey(lock.pack_id, lock.template_id, lock.version)),
        )

    def _stale_packs(self, key: TemplateKey) -> StalePacks | None:
        if self._packs is None:
            return None
        source = self._packs.describe()
        if not source.lags_for(key):
            return None
        return StalePacks(path=source.path, studio_version=source.builtin_studio or "")


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
