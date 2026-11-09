"""Что эта Студия может делать с проектом: полный доступ, только чтение, только файлы.

Причины ограничения:

* данные проекта записаны более новой Студией (core.project_schema): `read_compat`
  выше нашей схемы — только файлы, `write_compat` выше — только чтение;
* версии шаблона проекта нет в этой Студии (проект обновлён более новой
  Студией, потом Студию откатили): без манифеста не работают сборка, проверки,
  подписи и сдача — только чтение, с подсказкой «нужна Студия ≥ X». Если же
  версия вшита в эту Студию, но каталог шаблонов подключён извне и отстаёт
  (core.template_packs), виновата не Студия: подсказка называет каталог;
* идёт обновление шаблона: на время транзакции — только чтение.

Запреты исполняет HTTP-гард (api.guards) для всех запросов на запись в проект и,
последним рубежом, репозитории состояния (infra.persistence.project).
"""

from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import ProjectAccessMode, ProjectAccessReason
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.project_schema import schema_access

_MODE_ORDER = {ProjectAccessMode.full: 0, ProjectAccessMode.read_only: 1, ProjectAccessMode.files_only: 2}


@dataclass(frozen=True)
class StalePacks:
    """Версия шаблона вшита в эту Студию, но подключённого каталога шаблонов она не знает."""

    # Каталог шаблонов, как его видит Студия.
    path: str
    # Версия этой Студии: от неё каталог и отстаёт.
    studio_version: str


@dataclass(frozen=True)
class ProjectAccess:
    mode: ProjectAccessMode = ProjectAccessMode.full
    reasons: tuple[ProjectAccessReason, ...] = ()
    # Версия Студии, которая откроет проект полностью (если известна).
    required_studio: str | None = None
    # Шаблона нет из-за отставшего подключённого каталога, а не из-за старой Студии.
    stale_packs: StalePacks | None = None

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
    stale_packs: StalePacks | None = None,
) -> ProjectAccess:
    """`stale_packs` задан, когда версии нет только в подключённом каталоге, а в саму Студию она вшита."""
    limits: list[tuple[ProjectAccessMode, ProjectAccessReason]] = []
    required: str | None = None
    by_schema = schema_access(project.schema)
    if by_schema != ProjectAccessMode.full:
        limits.append((by_schema, _SCHEMA_REASONS[by_schema]))
        required = project.schema.written_by or None
    stale = None if template_available else stale_packs
    if not template_available:
        limits.append((ProjectAccessMode.read_only, ProjectAccessReason.template_missing))
        # Отставший каталог чинится не обновлением Студии: её минимальную версию не советуем.
        if stale is None:
            required = project.lock.min_studio or required
    if update_in_progress:
        limits.append((ProjectAccessMode.read_only, ProjectAccessReason.update_in_progress))
    mode = max((m for m, _r in limits), key=_MODE_ORDER.__getitem__, default=ProjectAccessMode.full)
    return ProjectAccess(mode=mode, reasons=tuple(r for _m, r in limits), required_studio=required, stale_packs=stale)


def access_message(access: ProjectAccess, template_version: str) -> str:
    """Почему проект только для чтения, на языке интерфейса: для ответа 423 и инструментов агента."""
    if ProjectAccessReason.update_in_progress in access.reasons:
        return localized_error(
            "Идёт обновление шаблона проекта, изменения временно недоступны.",
            "The project template is being updated, changes are temporarily unavailable.",
        )
    if access.stale_packs is not None and not access.required_studio:
        stale = access.stale_packs
        return localized_error(
            f"Версии шаблона {template_version} нет в каталоге шаблонов {stale.path}: он подключён извне "
            f"и отстаёт от Студии v{stale.studio_version}. Обновите каталог или уберите подключение.",
            f"Template version {template_version} is missing from the template folder {stale.path}: "
            f"it is mounted from outside and lags behind Studio v{stale.studio_version}. "
            "Update the folder or remove the mount.",
        )
    if access.mode == ProjectAccessMode.files_only or access.required_studio:
        required = access.required_studio or "?"
        return localized_error(
            f"Проект сохранён более новой версией Студии (нужна {required}): здесь он открыт только для чтения.",
            f"The project was saved by a newer Studio (needs {required}): it is read-only here.",
        )
    return localized_error("Проект открыт только для чтения.", "The project is read-only.")
