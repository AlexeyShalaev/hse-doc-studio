from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.catalog import CheckRule
from hse_doc_studio.core.enums import CheckSeverity
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import CheckResolutionService
from hse_doc_studio.core.value_objects import ChecksOverride
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class ListDocumentCheckRulesInput:
    project_id: UUID
    doc_id: str


@dataclass(frozen=True)
class CheckRuleListItem:
    rule_id: str
    title: dict[str, str]
    description: dict[str, str]
    category: str | None
    effective_severity: CheckSeverity
    enabled: bool
    source: str
    # Подпись источника, объявленная САМИМ паком (checks/<source>.yaml -> label).
    # Пусто для синтетического "misc" и для паков без шапки — UI тогда покажет id.
    source_label: dict[str, str]


@dataclass
class ListDocumentCheckRulesOutput:
    rules: list[CheckRuleListItem]


def _rule_applies_to(rule: CheckRule, doc_id: str) -> bool:
    if rule.applies_to == "*":
        return True
    return isinstance(rule.applies_to, list) and doc_id in rule.applies_to


def _derive_source(rule_id: str) -> str:
    # Rule IDs are conventionally formatted as "<source>/<short-name>", where
    # <source> matches the YAML file basename (e.g. gost-7.32-2017,
    # hse-pi-methodology-2026). Surface that prefix so the UI can group rules
    # by GOST/methodology document.
    return rule_id.split("/", 1)[0] if "/" in rule_id else "misc"


class ListDocumentCheckRulesUC:
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

    async def execute(self, inp: ListDocumentCheckRulesInput) -> ListDocumentCheckRulesOutput:
        project_result = await self._get_project_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = project_result.project

        doc = next((d for d in project.documents if d.id == inp.doc_id), None)
        if doc is None:
            raise NotFoundError(
                localized_error(
                    f"Документ {inp.doc_id!r} не найден в проекте {inp.project_id}",
                    f"Document {inp.doc_id!r} not found in project {inp.project_id}",
                )
            )

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

        # `applies_to` пака перечисляет id ОПРЕДЕЛЕНИЙ — в team doc.id несёт
        # суффикс владельца, поэтому применимость считаем по def_id.
        applicable_rules = [r for r in version.rules if _rule_applies_to(r, doc.def_id)]

        # Pack-author may declare per-document overrides in version.yaml — e.g.
        # `pres` skipping formatting category. Pull it from DocumentDefinition.
        doc_def = next((d for d in version.documents if d.id == doc.def_id), None)
        doc_def_checks = doc_def.checks if doc_def is not None else ChecksOverride()

        resolved = self._check_resolution_service.resolve(
            rules=list(version.rules),
            doc_id=doc.def_id,
            version_cfg=version.checks_config,
            doc_definition_checks=doc_def_checks,
            project_override=project.checks_override,
            doc_override=doc.checks_override,
            user_override=ChecksOverride(),
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

        return ListDocumentCheckRulesOutput(rules=items)
