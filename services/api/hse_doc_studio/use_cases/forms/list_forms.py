from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.catalog import FormDefinition
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.repositories import (
    IFormStateRepository,
    IProjectIndexRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import FormValidationService
from hse_doc_studio.core.team import doc_instance_id, is_team, managed_authors
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class FormSummary:
    id: str
    title: dict[str, str]
    required_for_pack: bool
    completed: bool
    complete: bool
    icon: str | None
    # Team mode: слаг автора-владельца инстанса per-author формы (None — общая).
    owner: str | None = None


@dataclass
class ListFormsInput:
    project_id: UUID


@dataclass
class ListFormsOutput:
    forms: list[FormSummary]


class ListFormsUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        form_state_repo: IFormStateRepository,
        validation_service: FormValidationService,
    ) -> None:
        self._template_repo = template_repo
        self._form_state_repo = form_state_repo
        self._validation_service = validation_service
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: ListFormsInput) -> ListFormsOutput:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        version = self._template_repo.get_version(project.lock.pack_id, project.lock.template_id, project.lock.version)
        if version is None:
            return ListFormsOutput(forms=[])

        # Team: формы с per_author разворачиваются в инстанс на каждого
        # ведомого автора ("{form}--{slug}", тайтл получает ФИО) — у каждого
        # свой стейт ответов; общие формы остаются одним пунктом.
        team = is_team(project)
        summaries: list[FormSummary] = []
        for form in version.forms:
            # Формы гейтятся по виду проекта (supported_kinds), как документы:
            # research-форма (напр. «Ссылка на код») в программном виде не видна.
            if str(project.kind) not in form.supported_kinds:
                continue
            if team and form.per_author:
                for author in managed_authors(project):
                    if not author.slug:
                        continue
                    instance_id = doc_instance_id(form.id, author.slug)
                    title = {lang: f"{text} — {author.name}" for lang, text in form.title.items()} or {
                        "ru": author.name
                    }
                    summaries.append(self._summary(project, form, instance_id, title, owner=author.slug))
            else:
                summaries.append(self._summary(project, form, form.id, dict(form.title), owner=None))
        return ListFormsOutput(forms=summaries)

    def _summary(
        self,
        project: Project,
        form: FormDefinition,
        instance_id: str,
        title: dict[str, str],
        owner: str | None,
    ) -> FormSummary:
        state = self._form_state_repo.get_state(project.folder, instance_id)
        answers = state.answers if state is not None else {}
        completed = state.completed if state is not None else False
        errors = self._validation_service.validate(form, answers)
        return FormSummary(
            id=instance_id,
            title=title,
            required_for_pack=form.required_for_pack,
            completed=completed,
            complete=not errors,
            icon=form.icon,
            owner=owner,
        )
