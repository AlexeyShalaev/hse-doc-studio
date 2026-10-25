"""Что эта Студия может делать с проектом: полный доступ, только чтение, только файлы.

Причины ограничения:

* данные проекта записаны более новой Студией (core.project_schema): `read_compat`
  выше нашей схемы — только файлы, `write_compat` выше — только чтение;
* версии шаблона проекта нет в этой Студии (проект обновлён более новой
  Студией, потом Студию откатили): без манифеста не работают сборка, проверки,
  подписи и сдача — только чтение, с подсказкой «нужна Студия ≥ X»;
* идёт обновление шаблона: на время транзакции — только чтение.

Запреты исполняет HTTP-гард (api.guards) для всех запросов на запись в проект и,
последним рубежом, репозитории состояния (infra.persistence.project).
"""

from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import ProjectAccessMode, ProjectAccessReason
from hse_doc_studio.core.project_schema import schema_access

_MODE_ORDER = {ProjectAccessMode.full: 0, ProjectAccessMode.read_only: 1, ProjectAccessMode.files_only: 2}


@dataclass(frozen=True)
class ProjectAccess:
    mode: ProjectAccessMode = ProjectAccessMode.full
    reasons: tuple[ProjectAccessReason, ...] = ()
    # Версия Студии, которая откроет проект полностью (если известна).
    required_studio: str | None = None

    @property
    def writable(self) -> bool:
        return self.mode == ProjectAccessMode.full


_SCHEMA_REASONS = {
    ProjectAccessMode.files_only: ProjectAccessReason.schema_read,
    ProjectAccessMode.read_only: ProjectAccessReason.schema_write,
}


def evaluate_project_access(
    project: Project,
    *,
    template_available: bool,
    update_in_progress: bool,
) -> ProjectAccess:
    limits: list[tuple[ProjectAccessMode, ProjectAccessReason]] = []
    required: str | None = None
    by_schema = schema_access(project.schema)
    if by_schema != ProjectAccessMode.full:
        limits.append((by_schema, _SCHEMA_REASONS[by_schema]))
        required = project.schema.written_by or None
    if not template_available:
        limits.append((ProjectAccessMode.read_only, ProjectAccessReason.template_missing))
        required = project.lock.min_studio or required
    if update_in_progress:
        limits.append((ProjectAccessMode.read_only, ProjectAccessReason.update_in_progress))
    mode = max((m for m, _r in limits), key=_MODE_ORDER.__getitem__, default=ProjectAccessMode.full)
    return ProjectAccess(mode=mode, reasons=tuple(r for _m, r in limits), required_studio=required)
