from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository
from hse_doc_studio.core.signing_route.ports import ISigningRouteGate
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from hse_doc_studio.use_cases.template_update.planning import PlannedUpdate, TemplateUpdatePlanner
from hse_doc_studio.use_cases.template_update.signature_presets import held_docs


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
    восстанавливается и сохраняется в истории (refs/hse/template/…). Документы под
    маршрутом подписания план отмечает: их места подписей обновление не трогает."""

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        planner: TemplateUpdatePlanner,
        vcs_locks: IVcsFolderLocks,
        routes: ISigningRouteGate,
    ) -> None:
        self._get_uc = GetProjectUC(project_repo, project_index_repo)
        self._planner = planner
        self._locks = vcs_locks
        self._routes = routes

    async def execute(self, inp: PlanTemplateUpdateInput) -> PlanTemplateUpdateOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        async with self._locks.for_folder(project.folder):
            held = await held_docs(self._routes, project)
            planned = await asyncio.to_thread(self._planner.plan, project, inp.to_version, held_docs=held)
        return PlanTemplateUpdateOutput(planned=planned)
