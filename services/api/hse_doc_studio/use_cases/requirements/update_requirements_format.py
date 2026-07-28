from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository
from hse_doc_studio.core.services import RequirementMatchingService
from hse_doc_studio.core.value_objects import RequirementsFormat
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC


@dataclass
class UpdateRequirementsFormatInput:
    project_id: UUID
    # None clears the per-project override, reverting to the pack template default.
    requirements_format: RequirementsFormat | None


@dataclass
class UpdateRequirementsFormatOutput:
    requirements_format: RequirementsFormat | None


class UpdateRequirementsFormatUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        matching_service: RequirementMatchingService,
    ) -> None:
        self._project_repo = project_repo
        self._matching_service = matching_service
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: UpdateRequirementsFormatInput) -> UpdateRequirementsFormatOutput:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        if inp.requirements_format is not None:
            # Validate patterns up front so an invalid regex is rejected on save
            # instead of silently breaking the scan later.
            self._matching_service.compile(inp.requirements_format)

        project.requirements_format = inp.requirements_format
        project.updated_at = datetime.now(UTC)
        self._project_repo.save(project)
        return UpdateRequirementsFormatOutput(requirements_format=inp.requirements_format)
