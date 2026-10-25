"""Раскладка проекта глазами обновления шаблона."""

from __future__ import annotations

from collections.abc import Callable

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.team import prefix_path, project_bases


def dynamic_output_paths(project: Project, version: TemplateVersion) -> frozenset[str]:
    """Выходы dynamic include во всех базах: их пишет сборка, а не пользователь."""
    return frozenset(
        prefix_path(base_dir, inc.output.strip("/"))
        for base_dir, _author in project_bases(project)
        for inc in version.dynamic_includes
    )


def doc_resolver(project: Project, version: TemplateVersion) -> Callable[[str], str | None]:
    """Путь файла → id инстанса документа, которому он принадлежит (или None)."""
    dir_map = ProjectTemplateService().instance_dir_map(project, version)
    prefixes = sorted(dir_map, key=len, reverse=True)

    def resolve(path: str) -> str | None:
        lowered = path.lower()
        for prefix in prefixes:
            if lowered.startswith(prefix + "/"):
                return dir_map[prefix]
        return None

    return resolve
