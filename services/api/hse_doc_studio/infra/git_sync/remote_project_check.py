"""Проверка `project.json` из чужой ветки тем же разбором, каким загрузчик проекта читает свой."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from hse_doc_studio.core.entities import Project
from hse_doc_studio.infra.persistence.serializers import deserialize_project


class ProjectDocumentCheck:
    def is_loadable(self, document: Mapping[str, Any]) -> bool:
        try:
            project = deserialize_project(dict(document), Path("."))
        except Exception:  # noqa: BLE001 — чужие данные: любая ошибка разбора значит «проект не откроется»
            return False
        return _has_expected_types(project)


def _has_expected_types(project: Project) -> bool:
    """Разборщик не проверяет типы простых полей, а ответы API проверяют: `meta` списком давал бы ошибку 500."""
    return (
        isinstance(project.name, str)
        and isinstance(project.meta, dict)
        and all(isinstance(author.name, str) and isinstance(author.meta, dict) for author in project.authors)
    )
