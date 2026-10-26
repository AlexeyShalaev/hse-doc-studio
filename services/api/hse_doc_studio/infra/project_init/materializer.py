from __future__ import annotations

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.repositories import ITemplateRepository
from hse_doc_studio.infra.project_init.template_renderer import instantiate_nda, regenerate_dynamic_includes


class TemplateMaterializer:
    """Порт ITemplateMaterializer поверх функций template_renderer."""

    def __init__(self, template_repo: ITemplateRepository) -> None:
        self._template_repo = template_repo

    def regenerate_dynamic_includes(self, project: Project, version: TemplateVersion) -> None:
        regenerate_dynamic_includes(project, version, self._template_repo)

    def instantiate_nda(self, project: Project, version: TemplateVersion) -> list[str]:
        return instantiate_nda(project, version, self._template_repo)
