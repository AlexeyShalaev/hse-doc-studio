"""Ближайший срок контрольной точки у проектов списка локальной Студии (docs/design/signing-route.md, 16.6).

На сервере список строится по каталогу в базе и берёт срок из копии `projects.deadlines`; локально список читает
`project.json` каждой папки, поэтому срок считается здесь: по срокам проекта, названиям точек в версии шаблона и
журналу сдачи. Проекты без сроков журнал не читают.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from hse_doc_studio.core.checkpoint_deadlines import NextDeadline, project_next_deadline
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.repositories import IPackSubmissionRepository, ITemplateRepository
from hse_doc_studio.use_cases.submission.set_checkpoint_deadline import built_times


class ProjectNextDeadlinesUC:
    def __init__(self, template_repo: ITemplateRepository, submission_repo: IPackSubmissionRepository) -> None:
        self._template_repo = template_repo
        self._submission_repo = submission_repo

    async def execute(self, projects: Sequence[Project]) -> dict[UUID, NextDeadline]:
        now = datetime.now(UTC)
        result: dict[UUID, NextDeadline] = {}
        for project in projects:
            if not project.deadlines:
                continue
            lock = project.lock
            version = self._template_repo.get_version(lock.pack_id, lock.template_id, lock.version)
            if version is None:
                continue
            names = {profile.id: dict(profile.name) for profile in version.pack_submission.profiles}
            built = await built_times(self._submission_repo, project)
            found = project_next_deadline(project.deadlines, names, built, now=now)
            if found is not None:
                result[project.id] = found
        return result
