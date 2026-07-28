from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.enums import VcsTagKind
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository
from hse_doc_studio.core.vcs.entities import VcsTag
from hse_doc_studio.core.vcs.errors import VcsUnavailableError
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks, IVcsService
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class ListVcsTagsInput:
    project_id: UUID


@dataclass
class ListVcsTagsOutput:
    tags: list[VcsTag]


class ListVcsTagsUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        vcs_service: IVcsService,
    ) -> None:
        self._vcs = vcs_service
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: ListVcsTagsInput) -> ListVcsTagsOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        tags = await asyncio.to_thread(self._vcs.list_tags, project)
        return ListVcsTagsOutput(tags=tags)


@dataclass
class CreateVcsTagInput:
    project_id: UUID
    name: str
    commit_id: str | None = None
    message: str | None = None
    kind: VcsTagKind = VcsTagKind.tag


@dataclass
class CreateVcsTagOutput:
    tag: VcsTag


class CreateVcsTagUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        vcs_service: IVcsService,
        locks: IVcsFolderLocks,
    ) -> None:
        self._vcs = vcs_service
        self._locks = locks
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: CreateVcsTagInput) -> CreateVcsTagOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        if not self._vcs.is_available(project):
            raise VcsUnavailableError(
                localized_error(
                    f"папка проекта недоступна: {project.folder}",
                    f"project folder not accessible: {project.folder}",
                )
            )
        async with self._locks.for_folder(project.folder):
            tag = await asyncio.to_thread(
                lambda: self._vcs.create_tag(
                    project,
                    name=inp.name,
                    commit_id=inp.commit_id,
                    message=inp.message,
                    kind=inp.kind,
                )
            )
        logger.info("vcs tag created", project_id=str(inp.project_id), name=inp.name)
        return CreateVcsTagOutput(tag=tag)


@dataclass
class DeleteVcsTagInput:
    project_id: UUID
    name: str


@dataclass
class DeleteVcsTagOutput:
    deleted: bool


class DeleteVcsTagUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        vcs_service: IVcsService,
        locks: IVcsFolderLocks,
    ) -> None:
        self._vcs = vcs_service
        self._locks = locks
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: DeleteVcsTagInput) -> DeleteVcsTagOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        if not self._vcs.is_available(project):
            raise VcsUnavailableError(
                localized_error(
                    f"папка проекта недоступна: {project.folder}",
                    f"project folder not accessible: {project.folder}",
                )
            )
        async with self._locks.for_folder(project.folder):
            await asyncio.to_thread(lambda: self._vcs.delete_tag(project, name=inp.name))
        logger.info("vcs tag deleted", project_id=str(inp.project_id), name=inp.name)
        return DeleteVcsTagOutput(deleted=True)
