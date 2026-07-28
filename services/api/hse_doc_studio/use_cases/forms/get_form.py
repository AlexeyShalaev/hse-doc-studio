from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.catalog import FormDefinition
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IFormStateRepository,
    IProjectIndexRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import FormValidationService, resolve_form_instance
from hse_doc_studio.core.value_objects import FormState, FormValidationError
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class GetFormInput:
    project_id: UUID
    form_id: str


@dataclass
class GetFormOutput:
    form: FormDefinition
    state: FormState
    complete: bool
    errors: list[FormValidationError]
    required_for_pack: bool


class GetFormUC:
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

    async def execute(self, inp: GetFormInput) -> GetFormOutput:
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
        # Team: per-author формы адресуются инстансами "{form}--{slug}"; стейт
        # ответов лежит под id инстанса.
        form, _author = resolve_form_instance(project, version, inp.form_id)

        state = self._form_state_repo.get_state(project.folder, inp.form_id)
        if state is None:
            state = FormState.empty(form.schema_version)

        errors = self._validation_service.validate(form, state.answers)
        return GetFormOutput(
            form=form,
            state=state,
            complete=not errors,
            errors=errors,
            required_for_pack=form.required_for_pack,
        )
