"""Поля проекта, от которых зависят права: источник правды БД, а `project.json` лишь их копия.

Гард на каждом запросе читает строку проекта и кладёт значения сюда; репозиторий проектов
подставляет их поверх прочитанного файла и при записи. Так команда, чей git подтянул чужой
`project.json`, не меняет ни права, ни состав общих документов.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import UUID

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import ProjectStaffing


@dataclass(frozen=True)
class AclFlags:
    team: bool
    shared_enabled: bool

    def apply(self, project: Project) -> Project:
        staffing = ProjectStaffing.team if self.team else ProjectStaffing.solo
        if project.staffing == staffing and project.shared_enabled == self.shared_enabled:
            return project
        return replace(project, staffing=staffing, shared_enabled=self.shared_enabled)


class AclFlagsCache:
    def __init__(self) -> None:
        self._flags: dict[UUID, AclFlags] = {}

    def put(self, project_id: UUID, flags: AclFlags) -> None:
        self._flags[project_id] = flags

    def get(self, project_id: UUID) -> AclFlags | None:
        return self._flags.get(project_id)
