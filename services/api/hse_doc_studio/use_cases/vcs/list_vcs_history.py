from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import UUID

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository, ITemplateRepository
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.vcs.entities import VcsCommit
from hse_doc_studio.core.vcs.protocols import IVcsService
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC


@dataclass
class ListVcsHistoryInput:
    project_id: UUID
    doc_id: str | None = None
    limit: int = 50
    offset: int = 0


@dataclass
class ListVcsHistoryOutput:
    commits: list[VcsCommit]


class ListVcsHistoryUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        vcs_service: IVcsService,
        template_repo: ITemplateRepository | None = None,
    ) -> None:
        self._vcs = vcs_service
        self._template_repo = template_repo
        self._template_service = ProjectTemplateService()
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: ListVcsHistoryInput) -> ListVcsHistoryOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        pathspec = self._doc_pathspec(project, inp.doc_id)
        commits = await asyncio.to_thread(
            lambda: self._vcs.log(project, doc_id=pathspec, limit=inp.limit, offset=inp.offset)
        )
        return ListVcsHistoryOutput(commits=commits)

    def _doc_pathspec(self, project: Project, doc_id: str | None) -> str | None:
        """git-pathspec папки документа: инстанс-id («vkr--shalaev») — не имя
        каталога, поэтому фильтр строится из пути главного .tex («shalaev/vkr»).
        Фолбэк — сам doc_id (легаси-раскладка doc_id==папка)."""
        if not doc_id or self._template_repo is None:
            return doc_id
        doc = next((d for d in project.documents if d.id == doc_id), None)
        if doc is None:
            return doc_id
        version = self._template_repo.get_version(project.lock.pack_id, project.lock.template_id, project.lock.version)
        if version is None:
            return doc_id
        try:
            source_file, _ = self._template_service.resolve_instance_source(project, doc, version)
        except (ValueError, NotFoundError):
            return doc_id
        parent = PurePosixPath(source_file.replace("\\", "/")).parent.as_posix()
        return doc_id if parent in ("", ".") else parent
