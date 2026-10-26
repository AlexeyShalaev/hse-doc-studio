from __future__ import annotations

from typing import Protocol

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.entities import Project


class ITemplateMaterializer(Protocol):
    # Выкладывает в папку проекта файлы, зависящие от текущего состояния проекта.
    def regenerate_dynamic_includes(self, project: Project, version: TemplateVersion) -> None: ...

    def instantiate_nda(self, project: Project, version: TemplateVersion) -> list[str]: ...
