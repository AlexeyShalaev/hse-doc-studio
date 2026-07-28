from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import Lang, ProjectStaffing
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
)
from hse_doc_studio.core.team import normalize_team_authors
from hse_doc_studio.core.value_objects import Author, ChecksOverride, Person
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()

_MISSING = object()


@dataclass
class UpdateProjectInput:
    project_id: UUID
    name: str | None = None
    lang: Lang | None = None
    meta: dict[str, Any] | None = None
    authors: list[Author] | None = None
    supervisor: Person | None = _MISSING  # type: ignore[assignment]
    co_supervisor: Person | None = _MISSING  # type: ignore[assignment]
    academic_supervisor: Person | None = _MISSING  # type: ignore[assignment]
    pinned: bool | None = None
    archived: bool | None = None
    checks_override: ChecksOverride | None = None


@dataclass
class UpdateProjectOutput:
    project: Project


class UpdateProjectUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
    ) -> None:
        self._project_repo = project_repo
        self._project_index_repo = project_index_repo
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: UpdateProjectInput) -> UpdateProjectOutput:  # noqa: C901
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        if inp.name is not None:
            project.name = inp.name
        if inp.lang is not None:
            project.lang = inp.lang
        if inp.meta is not None:
            project.meta = {**project.meta, **inp.meta}
        if inp.authors is not None:
            # Team: каждому автору гарантируется валидный уникальный слаг
            # (новый автор из настроек приходит без него; слаг — ключ папки,
            # без него комплект нельзя довключить).
            if project.staffing == ProjectStaffing.team:
                project.authors = normalize_team_authors(inp.authors)
            else:
                project.authors = inp.authors
        if inp.supervisor is not _MISSING:
            project.supervisor = inp.supervisor
        if inp.co_supervisor is not _MISSING:
            project.co_supervisor = inp.co_supervisor
        if inp.academic_supervisor is not _MISSING:
            project.academic_supervisor = inp.academic_supervisor
        if inp.pinned is not None:
            project.pinned = inp.pinned
        if inp.archived is not None:
            project.archived = inp.archived
        if inp.checks_override is not None:
            project.checks_override = inp.checks_override

        project.updated_at = datetime.now(tz=timezone.utc)
        self._project_repo.save(project)

        logger.info("project updated", project_id=str(inp.project_id))
        return UpdateProjectOutput(project=project)
