"""Срок контрольной точки проекта (docs/design/signing-route.md, 16.3 и 16.8).

Срок пишется в `project.json` (`Project.deadlines`) и копией в каталог проектов (её делает репозиторий проектов
сервера на сохранение). Точку ищем в версии шаблона проекта: неизвестная точка 404. Срок в прошлом можно поставить:
его ставят и задним числом, чтобы видеть «просрочено». Тот же срок ничего не пишет и в аудит не попадает.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import structlog

from hse_doc_studio.core.checkpoint_deadlines import CheckpointDeadline, checkpoint_deadline, parse_deadline
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IPackSubmissionRepository,
    IProjectIndexRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.signatures.ports import ISignatureAudit
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()

AUDIT_DEADLINE = "project.deadline"


@dataclass
class SetCheckpointDeadlineInput:
    project_id: UUID
    profile_id: str
    # ISO 8601 с поясом; None снимает срок.
    deadline: str | None


async def built_times(submissions: IPackSubmissionRepository, project: Project) -> dict[str, list[datetime]]:
    """Моменты сборки пакетов проекта по точкам: по ним срок точки становится «пакет собран» или «просрочено»."""
    built: dict[str, list[datetime]] = {}
    for record in await submissions.list_for_project(project.folder):
        moment = record.created_at if record.created_at.tzinfo else record.created_at.replace(tzinfo=UTC)
        built.setdefault(record.profile_id, []).append(moment)
    return built


def unknown_checkpoint(profile_id: str) -> NotFoundError:
    return NotFoundError(
        localized_error(
            f"Контрольной точки «{profile_id}» нет в версии шаблона проекта",
            f"The checkpoint «{profile_id}» is not in the project's template version",
        )
    )


class SetCheckpointDeadlineUC:
    def __init__(  # noqa: PLR0913 — порты сценария перечислены явно
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        submission_repo: IPackSubmissionRepository,
        audit: ISignatureAudit | None = None,
    ) -> None:
        self._project_repo = project_repo
        self._template_repo = template_repo
        self._submission_repo = submission_repo
        self._audit = audit
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: SetCheckpointDeadlineInput) -> CheckpointDeadline:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        lock = project.lock
        version = self._template_repo.get_version(lock.pack_id, lock.template_id, lock.version)
        if version is None or all(p.id != inp.profile_id for p in version.pack_submission.profiles):
            raise unknown_checkpoint(inp.profile_id)
        moment = parse_deadline(inp.deadline) if inp.deadline is not None else None
        previous = project.deadlines.get(inp.profile_id)
        if moment != previous:
            deadlines = {k: v for k, v in project.deadlines.items() if k != inp.profile_id}
            if moment is not None:
                deadlines[inp.profile_id] = moment
            project.deadlines = deadlines
            project.updated_at = datetime.now(UTC)
            self._project_repo.save(project)
            logger.info("checkpoint deadline set", project_id=str(inp.project_id), profile_id=inp.profile_id)
            if self._audit is not None:
                await self._audit.record(
                    AUDIT_DEADLINE,
                    project_id=inp.project_id,
                    details={
                        "profile_id": inp.profile_id,
                        "previous": previous.isoformat() if previous is not None else None,
                        "deadline": moment.isoformat() if moment is not None else None,
                    },
                )
        built = await built_times(self._submission_repo, project) if moment is not None else {}
        return checkpoint_deadline(inp.profile_id, moment, built.get(inp.profile_id, ()), now=datetime.now(UTC))
