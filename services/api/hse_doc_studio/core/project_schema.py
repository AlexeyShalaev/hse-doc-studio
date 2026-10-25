"""Формат данных проекта (`.hse-studio/*.json`) и совместимость между Студиями.

Студию можно переключить на любую опубликованную версию, включая откат, поэтому
«старая Студия открывает проект, записанный новой» — штатный сценарий. Правило
как у заголовка SQLite: в `project.json` лежит блок

    "schema": {"version": 2, "read_compat": 1, "write_compat": 2, "written_by": "0.3.0"}

* `version` — формат данных; один номер на весь набор `.hse-studio/*.json`
  (миграция часто трогает несколько файлов сразу);
* `read_compat` — минимальная версия схемы, которой хватает, чтобы ЧИТАТЬ данные;
  если она выше нашей — показываем только файлы;
* `write_compat` — минимальная версия, которой можно ПИСАТЬ; выше нашей — только
  чтение.

Неизвестные поля при записи сохраняются (infra.persistence.unknown_fields),
поэтому аддитивное изменение (новое необязательное поле) `write_compat` не
поднимает. Поднимать его нужно, когда старый писатель испортил бы данные:
новое значение enum в сохраняемом состоянии, поле, которое надо держать
согласованным с другим, смена смысла существующего поля.

Отсутствие блока — схема 1: формат всех проектов до появления этого модуля.
"""

from __future__ import annotations

from hse_doc_studio.core.enums import ProjectAccessMode
from hse_doc_studio.core.value_objects import ProjectSchema

# Версия схемы, которую пишет эта Студия, и минимальные версии читателя/писателя
# для её данных. Подъём версии сопровождается шагом в
# infra.persistence.project_migrations.
PROJECT_SCHEMA_VERSION = 1
PROJECT_SCHEMA_READ_COMPAT = 1
PROJECT_SCHEMA_WRITE_COMPAT = 1

LEGACY_PROJECT_SCHEMA = ProjectSchema(version=1, read_compat=1, write_compat=1)


def current_schema(app_version: str) -> ProjectSchema:
    return ProjectSchema(
        version=PROJECT_SCHEMA_VERSION,
        read_compat=PROJECT_SCHEMA_READ_COMPAT,
        write_compat=PROJECT_SCHEMA_WRITE_COMPAT,
        written_by=app_version,
    )


def schema_to_write(stored: ProjectSchema | None, app_version: str) -> ProjectSchema:
    """Блок схемы для записи поверх `stored` (то, что лежит на диске).

    Писать поверх данных более новой схемы можно, только если она это
    разрешила (`write_compat` не выше нашей). Тогда её номер и требования
    сохраняются: неизвестные поля мы не теряем, но и понизить формат не вправе.
    """
    ours = current_schema(app_version)
    if stored is None:
        return ours
    return ProjectSchema(
        version=max(stored.version, ours.version),
        read_compat=max(stored.read_compat, ours.read_compat),
        write_compat=max(stored.write_compat, ours.write_compat),
        written_by=app_version,
    )


def schema_access(schema: ProjectSchema) -> ProjectAccessMode:
    """Что эта Студия может делать с данными такой схемы."""
    if schema.read_compat > PROJECT_SCHEMA_VERSION:
        return ProjectAccessMode.files_only
    if schema.write_compat > PROJECT_SCHEMA_VERSION:
        return ProjectAccessMode.read_only
    return ProjectAccessMode.full


def can_write(schema: ProjectSchema | None) -> bool:
    return schema is None or schema.write_compat <= PROJECT_SCHEMA_VERSION
