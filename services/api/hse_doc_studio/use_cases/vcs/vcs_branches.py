from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.i18n import current_interface_language, localized_error
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository
from hse_doc_studio.core.vcs.entities import VcsBranch, VcsSettings, VcsStatus
from hse_doc_studio.core.vcs.errors import VcsUnavailableError
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks, IVcsService
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class ListVcsBranchesInput:
    project_id: UUID


@dataclass
class ListVcsBranchesOutput:
    branches: list[VcsBranch]


class ListVcsBranchesUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        vcs_service: IVcsService,
    ) -> None:
        self._vcs = vcs_service
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: ListVcsBranchesInput) -> ListVcsBranchesOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        branches = await asyncio.to_thread(self._vcs.list_branches, project)
        return ListVcsBranchesOutput(branches=branches)


@dataclass
class CreateVcsBranchInput:
    project_id: UUID
    name: str
    from_commit: str | None = None
    switch: bool = True


@dataclass
class CreateVcsBranchOutput:
    branch: VcsBranch


class CreateVcsBranchUC:
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

    async def execute(self, inp: CreateVcsBranchInput) -> CreateVcsBranchOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        if not self._vcs.is_available(project):
            raise VcsUnavailableError(
                localized_error(
                    f"папка проекта недоступна: {project.folder}",
                    f"project folder not accessible: {project.folder}",
                )
            )
        settings = VcsSettings.from_meta(project.meta)
        async with self._locks.for_folder(project.folder):
            branch = await asyncio.to_thread(
                lambda: self._vcs.create_branch(
                    project,
                    settings,
                    name=inp.name,
                    from_commit=inp.from_commit,
                    switch=inp.switch,
                )
            )
        logger.info("vcs branch created", project_id=str(inp.project_id), name=inp.name)
        return CreateVcsBranchOutput(branch=branch)


@dataclass
class SwitchVcsBranchInput:
    project_id: UUID
    name: str


@dataclass
class SwitchVcsBranchOutput:
    status: VcsStatus


class SwitchVcsBranchUC:
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

    async def execute(self, inp: SwitchVcsBranchInput) -> SwitchVcsBranchOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        if not self._vcs.is_available(project):
            raise VcsUnavailableError(
                localized_error(
                    f"папка проекта недоступна: {project.folder}",
                    f"project folder not accessible: {project.folder}",
                )
            )
        settings = VcsSettings.from_meta(project.meta)
        async with self._locks.for_folder(project.folder):
            status = await asyncio.to_thread(lambda: self._vcs.switch_branch(project, settings, name=inp.name))
        logger.info("vcs branch switched", project_id=str(inp.project_id), name=inp.name)
        return SwitchVcsBranchOutput(status=status)


@dataclass
class DeleteVcsBranchInput:
    project_id: UUID
    name: str


@dataclass
class DeleteVcsBranchOutput:
    deleted: bool


class DeleteVcsBranchUC:
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

    async def execute(self, inp: DeleteVcsBranchInput) -> DeleteVcsBranchOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        if not self._vcs.is_available(project):
            raise VcsUnavailableError(
                localized_error(
                    f"папка проекта недоступна: {project.folder}",
                    f"project folder not accessible: {project.folder}",
                )
            )
        branches = await asyncio.to_thread(self._vcs.list_branches, project)
        current = next((b for b in branches if b.is_current), None)
        en = current_interface_language() is Lang.en
        if current is not None and current.name == inp.name:
            raise ValueError("The current branch cannot be deleted" if en else "Нельзя удалить текущую ветку")
        target = next((b for b in branches if b.name == inp.name), None)
        if target is not None and target.is_protected:
            raise ValueError("The main branch cannot be deleted" if en else "Нельзя удалить основную ветку")
        async with self._locks.for_folder(project.folder):
            await asyncio.to_thread(lambda: self._vcs.delete_branch(project, name=inp.name))
        logger.info("vcs branch deleted", project_id=str(inp.project_id), name=inp.name)
        return DeleteVcsBranchOutput(deleted=True)
