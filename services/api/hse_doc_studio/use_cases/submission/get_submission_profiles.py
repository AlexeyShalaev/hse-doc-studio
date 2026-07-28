from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.catalog import SubmissionProfile
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class GetSubmissionProfilesInput:
    project_id: UUID


@dataclass
class GetSubmissionProfilesOutput:
    profiles: list[SubmissionProfile]


class GetSubmissionProfilesUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
    ) -> None:
        self._template_repo = template_repo
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: GetSubmissionProfilesInput) -> GetSubmissionProfilesOutput:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        template_version = self._template_repo.get_version(
            project.lock.pack_id,
            project.lock.template_id,
            project.lock.version,
        )
        if template_version is None:
            logger.warning(
                "template version not found for project",
                project_id=str(inp.project_id),
                lock=str(project.lock),
            )
            return GetSubmissionProfilesOutput(profiles=[])

        profiles = list(template_version.pack_submission.profiles)
        return GetSubmissionProfilesOutput(profiles=profiles)
