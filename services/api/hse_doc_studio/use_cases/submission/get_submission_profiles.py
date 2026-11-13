from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

import structlog

from hse_doc_studio.core.catalog import SubmissionProfile
from hse_doc_studio.core.checkpoint_deadlines import CheckpointDeadline, checkpoint_deadline
from hse_doc_studio.core.repositories import (
    IPackSubmissionRepository,
    IProjectIndexRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.signing_route.preset import RoutePreset
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from hse_doc_studio.use_cases.signing_route.point import build_point
from hse_doc_studio.use_cases.signing_route.preset import route_preset
from hse_doc_studio.use_cases.submission.set_checkpoint_deadline import built_times

logger = structlog.get_logger()


@dataclass
class GetSubmissionProfilesInput:
    project_id: UUID


@dataclass
class GetSubmissionProfilesOutput:
    profiles: list[SubmissionProfile]
    # Срок каждой точки и его состояние (signing-route.md, 16.6), по id профиля; у точки без срока `none`.
    deadlines: dict[str, CheckpointDeadline] = field(default_factory=dict)
    # Пресет маршрута точки на людях проекта сейчас (signing-route.md, 15.12), по id профиля; только у точек, для
    # которых версия шаблона его задаёт, и только если сценарию дали `template_service` (MCP).
    presets: dict[str, RoutePreset] = field(default_factory=dict)


class GetSubmissionProfilesUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        submission_repo: IPackSubmissionRepository | None = None,
        template_service: ProjectTemplateService | None = None,
    ) -> None:
        self._template_repo = template_repo
        self._submission_repo = submission_repo
        self._template_service = template_service
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
        # Журнал сдачи читается, только если сроки есть: состояние «пакет собран» нужно лишь сроку.
        built = (
            await built_times(self._submission_repo, project)
            if project.deadlines and self._submission_repo is not None
            else {}
        )
        now = datetime.now(UTC)
        deadlines = {
            p.id: checkpoint_deadline(p.id, project.deadlines.get(p.id), built.get(p.id, ()), now=now) for p in profiles
        }
        presets: dict[str, RoutePreset] = {}
        if self._template_service is not None:
            for profile in profiles:
                preset = route_preset(build_point(project, template_version, profile, self._template_service))
                if preset is not None:
                    presets[profile.id] = preset
        return GetSubmissionProfilesOutput(profiles=profiles, deadlines=deadlines, presets=presets)
