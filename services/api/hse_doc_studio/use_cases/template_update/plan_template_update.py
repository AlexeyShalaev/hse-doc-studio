from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from hse_doc_studio.use_cases.template_update.planning import PlannedUpdate, TemplateUpdatePlanner


@dataclass
class PlanTemplateUpdateInput:
    project_id: UUID
    to_version: str


@dataclass
class PlanTemplateUpdateOutput:
    planned: PlannedUpdate


class PlanTemplateUpdateUC:
    """Предпросмотр обновления (dry-run): что станет с каждым файлом. На диске
    проекта ничего не меняется; база текущей версии, если её не было,
    восстанавливается и сохраняется в истории (refs/hse/template/…)."""

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        planner: TemplateUpdatePlanner,
        vcs_locks: IVcsFolderLocks,
    ) -> None:
        self._get_uc = GetProjectUC(project_repo, project_index_repo)
        self._planner = planner
        self._locks = vcs_locks

    async def execute(self, inp: PlanTemplateUpdateInput) -> PlanTemplateUpdateOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        async with self._locks.for_folder(project.folder):
            planned = await asyncio.to_thread(self._planner.plan, project, inp.to_version)
        return PlanTemplateUpdateOutput(planned=planned)
