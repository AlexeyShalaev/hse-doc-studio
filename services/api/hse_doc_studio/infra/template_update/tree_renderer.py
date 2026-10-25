"""Чистый рендер версии шаблона для проекта — в памяти, без записи в проект.

Тот же код, что и создание проекта (`instantiate_base` по базам команды и
`instantiate_nda`), только в теневую копию проекта во временном каталоге.
Поэтому нетронутый проект после обновления совпадает с новым проектом на
целевой версии — это главный критерий корректности обновления.

Выходы dynamic include сюда не входят: их перегенерирует каждая сборка.
"""

from __future__ import annotations

import tempfile
from dataclasses import replace
from pathlib import Path

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.repositories import ITemplateRepository
from hse_doc_studio.core.team import project_bases
from hse_doc_studio.infra.project_init.template_renderer import (
    TemplateRenderer,
    instantiate_base,
    instantiate_nda,
)


class TemplateTreeRenderer:
    def __init__(self, template_repo: ITemplateRepository, renderer: TemplateRenderer) -> None:
        self._template_repo = template_repo
        self._renderer = renderer

    def render(self, project: Project, version: TemplateVersion) -> dict[str, bytes]:
        with tempfile.TemporaryDirectory(prefix="hse-template-render-") as tmp:
            root = Path(tmp)
            shadow = replace(project, folder=root)
            for base_dir, author in project_bases(shadow):
                instantiate_base(
                    project=shadow,
                    version=version,
                    template_repo=self._template_repo,
                    renderer=self._renderer,
                    base_dir=base_dir,
                    author=author,
                )
            instantiate_nda(shadow, version, self._template_repo)
            return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}
