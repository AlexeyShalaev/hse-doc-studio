from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IFormStateRepository,
    IProjectIndexRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import resolve_form_instance
from hse_doc_studio.core.team import effective_meta
from hse_doc_studio.core.value_objects import Author, FormState
from hse_doc_studio.infra.forms.form_renderer import FormOutputRenderer
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class RenderFormInput:
    project_id: UUID
    form_id: str


@dataclass
class RenderFormOutput:
    content: str
    output_name: str
    format: str


def _build_context(project: Project, answers: dict[str, Any], author: Author | None = None) -> dict[str, Any]:
    """Jinja context for a form's output template: the project + raw answers.

    Mirrors the project-init `build_context` project shape and additionally
    exposes `project.supervisor` and `answers` so declaration-style templates
    can render signatures and per-answer tables.

    `author` — владелец инстанса per-author формы (team); solo — единственный
    автор. Шаблоны декларации подписываются `author.name`/`author.topic`, а не
    `authors[0]`.
    """
    if author is None and str(project.staffing) != "team" and project.authors:
        author = project.authors[0]
    supervisor = (
        {"name": project.supervisor.name, "title": project.supervisor.title} if project.supervisor is not None else {}
    )
    return {
        "project": {
            "name": project.name,
            "lang": str(project.lang),
            "kind": str(project.kind),
            "staffing": str(project.staffing),
            # Черновики (пустое имя) в официальный документ не попадают.
            "authors": [
                {"name": a.name, "group": a.group, "email": a.email} for a in project.authors if a.name.strip()
            ],
            "meta": effective_meta(project, author),
            "supervisor": supervisor,
            "created_at": project.created_at.isoformat(),
        },
        "author": (
            {
                "name": author.name,
                "group": author.group or "",
                "topic": author.topic or "",
                "meta": dict(author.meta),
            }
            if author is not None
            else {}
        ),
        "answers": answers,
    }


class RenderFormUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        form_state_repo: IFormStateRepository,
        renderer: FormOutputRenderer,
    ) -> None:
        self._template_repo = template_repo
        self._form_state_repo = form_state_repo
        self._renderer = renderer
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: RenderFormInput) -> RenderFormOutput:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        version = self._template_repo.get_version(project.lock.pack_id, project.lock.template_id, project.lock.version)
        if version is None:
            raise NotFoundError(
                localized_error(
                    f"форма {inp.form_id!r} не найдена для этого проекта",
                    f"form '{inp.form_id}' not found for this project",
                )
            )
        form, author = resolve_form_instance(project, version, inp.form_id)
        if form.output is None:
            raise ValueError(
                localized_error(
                    f"форма {inp.form_id!r} не имеет шаблона вывода",
                    f"form '{inp.form_id}' declares no output template",
                )
            )

        version_dir = self._template_repo.version_dir(
            project.lock.pack_id, project.lock.template_id, project.lock.version
        )
        if version_dir is None:
            raise NotFoundError(
                localized_error("Каталог версии шаблона не найден", "template version directory not found")
            )
        template_path = version_dir / form.output.template
        if not template_path.exists():
            raise NotFoundError(
                localized_error(
                    f"Шаблон вывода не найден: {form.output.template}",
                    f"output template not found: {form.output.template}",
                )
            )
        template_text = template_path.read_text(encoding="utf-8")

        state = self._form_state_repo.get_state(project.folder, inp.form_id)
        answers = state.answers if state is not None else FormState.empty(form.schema_version).answers

        content = self._renderer.render(template_text, _build_context(project, answers, author))
        return RenderFormOutput(
            content=content,
            output_name=form.output.output_name,
            format=form.output.format,
        )
