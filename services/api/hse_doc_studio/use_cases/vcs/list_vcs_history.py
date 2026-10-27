from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from uuid import UUID

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import VcsHistorySync
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository, ITemplateRepository
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.vcs.entities import VcsCommit, VcsHistoryFacets, VcsHistoryQuery
from hse_doc_studio.core.vcs.protocols import IVcsService
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC


@dataclass
class ListVcsHistoryInput:
    project_id: UUID
    doc_id: str | None = None
    limit: int = 50
    offset: int = 0
    kinds: tuple[str, ...] = ()
    author_email: str | None = None
    text: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    sync: VcsHistorySync | None = None


@dataclass
class ListVcsHistoryOutput:
    commits: list[VcsCommit]


@dataclass
class ListVcsHistoryFacetsInput:
    project_id: UUID
    doc_id: str | None = None


@dataclass
class ListVcsHistoryFacetsOutput:
    facets: VcsHistoryFacets


class _ProjectHistoryUC:
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

    async def _project_and_pathspec(self, project_id: UUID, doc_id: str | None) -> tuple[Project, str | None]:
        project = (await self._get_uc.execute(GetProjectInput(project_id=project_id))).project
        return project, self._doc_pathspec(project, doc_id)

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


class ListVcsHistoryUC(_ProjectHistoryUC):
    async def execute(self, inp: ListVcsHistoryInput) -> ListVcsHistoryOutput:
        project, pathspec = await self._project_and_pathspec(inp.project_id, inp.doc_id)
        query = VcsHistoryQuery(
            kinds=inp.kinds,
            author_email=inp.author_email,
            text=inp.text,
            since=inp.since,
            until=inp.until,
            sync=inp.sync,
        )
        commits = await asyncio.to_thread(
            lambda: self._vcs.log(project, doc_id=pathspec, limit=inp.limit, offset=inp.offset, query=query)
        )
        return ListVcsHistoryOutput(commits=commits)


class ListVcsHistoryFacetsUC(_ProjectHistoryUC):
    async def execute(self, inp: ListVcsHistoryFacetsInput) -> ListVcsHistoryFacetsOutput:
        project, pathspec = await self._project_and_pathspec(inp.project_id, inp.doc_id)
        facets = await asyncio.to_thread(lambda: self._vcs.history_facets(project, doc_id=pathspec))
        return ListVcsHistoryFacetsOutput(facets=facets)
