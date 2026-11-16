"""Раздел результата «проверки»: какие правила версии применимы к активным документам комплекта и какие выключены.

Считается только применимость (`applies_to`, `checks_version`), итог прогона нет: правила на Python и разбор TeX в
мгновенный расчёт не входят (раздел 8 дизайна, `out_of_scope`). Включённость решает тот же `CheckResolutionService`, что
у списка правил проекта.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hse_doc_studio.core.pack_studio.outcome.model import CheckRuleOutcome, DocumentOutcome, ElementRef
from hse_doc_studio.core.pack_studio.outcome.trace import Tracer, manifest_rule, why
from hse_doc_studio.core.services import CheckResolutionService
from hse_doc_studio.core.value_objects import ChecksOverride

if TYPE_CHECKING:
    from hse_doc_studio.core.catalog import CheckRule, TemplateVersion

VERSION_MANIFEST = "version.yaml"


def _applies_to(rule: CheckRule, active: tuple[str, ...]) -> tuple[str, ...]:
    if rule.applies_to == "*":
        return active
    return tuple(doc_id for doc_id in active if doc_id in rule.applies_to)


def evaluate_checks(
    version: TemplateVersion, documents: tuple[DocumentOutcome, ...], tracer: Tracer
) -> tuple[CheckRuleOutcome, ...]:
    active = tuple(doc.id for doc in documents if doc.state == "active")
    resolved = CheckResolutionService().resolve_for_project(
        rules=list(version.rules),
        doc_ids=set(active),
        version_cfg=version.checks_config,
        project_override=ChecksOverride(),
    )
    enabled = {rule.id: severity for rule, severity in resolved}
    config = version.checks_config
    rules: list[CheckRuleOutcome] = []
    for rule in version.rules:
        applies = _applies_to(rule, active)
        off_reason = None
        reasons: tuple[str, ...] = ()
        if rule.id not in enabled:
            if rule.id in config.disabled:
                off_reason = "disabled"
                pointer = "/checks_version/disabled"
            elif rule.category is not None and rule.category in config.disabled_categories:
                off_reason = "category_disabled"
                pointer = "/checks_version/disabled_categories"
            else:
                off_reason = "no_active_document"
                pointer = ""
            if pointer:
                reasons = why(
                    tracer.decide(
                        rule=manifest_rule(VERSION_MANIFEST, pointer),
                        kind="check_disabled",
                        effect="exclude",
                        terms=[],
                        actual={},
                        status="held",
                        subjects=[ElementRef("checks", rule.id)],
                    )
                )
        severity = enabled.get(rule.id) or config.severity_override.get(rule.id) or rule.default_severity
        rules.append(
            CheckRuleOutcome(
                id=rule.id,
                title=dict(rule.title),
                category=rule.category,
                severity=severity.value,  # type: ignore[arg-type]
                engine=rule.engine.value,
                enabled=rule.id in enabled,
                off_reason=off_reason,  # type: ignore[arg-type]
                applies_to=applies,
                why=reasons,
            )
        )
    return tuple(rules)
