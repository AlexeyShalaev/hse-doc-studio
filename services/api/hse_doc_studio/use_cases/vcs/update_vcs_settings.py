from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository
from hse_doc_studio.core.vcs.entities import VcsSettings
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class UpdateVcsSettingsInput:
    project_id: UUID
    # None = leave unchanged (partial patch).
    tracking_enabled: bool | None = None
    auto_commit_on_compile: bool | None = None
    track_pdf: bool | None = None


@dataclass
class UpdateVcsSettingsOutput:
    settings: VcsSettings


class UpdateVcsSettingsUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
    ) -> None:
        self._project_repo = project_repo
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: UpdateVcsSettingsInput) -> UpdateVcsSettingsOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        current = VcsSettings.from_meta(project.meta)
        updated = VcsSettings(
            tracking_enabled=current.tracking_enabled if inp.tracking_enabled is None else inp.tracking_enabled,
            auto_commit_on_compile=(
                current.auto_commit_on_compile if inp.auto_commit_on_compile is None else inp.auto_commit_on_compile
            ),
            track_pdf=current.track_pdf if inp.track_pdf is None else inp.track_pdf,
        )
        project.meta["vcs"] = updated.to_dict()
        self._project_repo.save(project)
        logger.info("vcs settings updated", project_id=str(inp.project_id))
        return UpdateVcsSettingsOutput(settings=updated)
