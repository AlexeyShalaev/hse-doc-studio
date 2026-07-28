from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.enums import CheckSeverity
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import CheckResolutionService
from hse_doc_studio.use_cases.checks.list_document_check_rules import (
    CheckRuleListItem,
    _derive_source,
)
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class ListProjectCheckRulesInput:
    project_id: UUID


@dataclass
class ListProjectCheckRulesOutput:
    rules: list[CheckRuleListItem]


class ListProjectCheckRulesUC:
    """List check rules applicable to any document in a project.

    Same shape as ListDocumentCheckRulesUC, but scoped to the project: returns
    every rule whose `applies_to` matches at least one document type in this
    project, with `enabled`/`effective_severity` computed after the version
    config and project-level override.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        check_resolution_service: CheckResolutionService,
    ) -> None:
        self._get_project_uc = GetProjectUC(project_repo, project_index_repo)
        self._template_repo = template_repo
        self._check_resolution_service = check_resolution_service

    async def execute(self, inp: ListProjectCheckRulesInput) -> ListProjectCheckRulesOutput:
        project_result = await self._get_project_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = project_result.project

        version = self._template_repo.get_version(
            project.lock.pack_id,
            project.lock.template_id,
            project.lock.version,
        )
        if version is None:
            version_ref = f"{project.lock.pack_id}/{project.lock.template_id}/{project.lock.version}"
            raise NotFoundError(
                localized_error(
                    f"Версия шаблона не найдена: {version_ref}", f"Template version not found: {version_ref}"
                )
            )

        doc_ids = {d.id for d in project.documents}

        applicable_rules = [
            r
            for r in version.rules
            if r.applies_to == "*" or (isinstance(r.applies_to, list) and any(d in r.applies_to for d in doc_ids))
        ]

        resolved = self._check_resolution_service.resolve_for_project(
            rules=list(version.rules),
            doc_ids=doc_ids,
            version_cfg=version.checks_config,
            project_override=project.checks_override,
        )
        enabled_severity_by_id: dict[str, CheckSeverity] = {rule.id: sev for rule, sev in resolved}

        # Подписи групп приходят из пака, а не зашиты в приложение: другой пак
        # может описывать другую ОП или вовсе другой вуз.
        source_labels = {s.id: dict(s.label) for s in version.check_sources}

        items: list[CheckRuleListItem] = []
        for rule in applicable_rules:
            source_id = _derive_source(rule.id)
            if rule.id in enabled_severity_by_id:
                effective = enabled_severity_by_id[rule.id]
                enabled = True
            else:
                effective = rule.default_severity
                enabled = False
            items.append(
                CheckRuleListItem(
                    rule_id=rule.id,
                    title=dict(rule.title),
                    description=dict(rule.description),
                    category=rule.category,
                    effective_severity=effective,
                    enabled=enabled,
                    source=source_id,
                    source_label=source_labels.get(source_id, {}),
                )
            )

        return ListProjectCheckRulesOutput(rules=items)
