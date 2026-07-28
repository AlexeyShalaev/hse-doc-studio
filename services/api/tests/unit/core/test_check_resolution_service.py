from __future__ import annotations

import pytest
from hse_doc_studio.core.catalog import ChecksVersionConfig
from hse_doc_studio.core.enums import CheckSeverity
from hse_doc_studio.core.services import CheckResolutionService
from hse_doc_studio.core.value_objects import ChecksOverride

from tests.factories import make_check_rule


@pytest.fixture
def service() -> CheckResolutionService:
    return CheckResolutionService()


@pytest.fixture
def no_override() -> ChecksOverride:
    return ChecksOverride()


@pytest.fixture
def empty_version_cfg() -> ChecksVersionConfig:
    return ChecksVersionConfig(disabled_categories=(), disabled=(), severity_override={})


def test__resolve__wildcard_applies_to__rule_included(
    service: CheckResolutionService, empty_version_cfg: ChecksVersionConfig, no_override: ChecksOverride
) -> None:
    rules = [make_check_rule("r1", applies_to="*")]

    result = service.resolve(rules, "any-doc", empty_version_cfg, no_override, no_override, no_override, no_override)

    assert len(result) == 1
    assert result[0][0].id == "r1"


def test__resolve__doc_specific_applies_to__included_only_for_matching_doc(
    service: CheckResolutionService, empty_version_cfg: ChecksVersionConfig, no_override: ChecksOverride
) -> None:
    rules = [make_check_rule("r1", applies_to=["tz"])]

    result_tz = service.resolve(rules, "tz", empty_version_cfg, no_override, no_override, no_override, no_override)
    result_vkr = service.resolve(rules, "vkr", empty_version_cfg, no_override, no_override, no_override, no_override)

    assert len(result_tz) == 1
    assert len(result_vkr) == 0


def test__resolve__version_disables_category__rule_excluded(
    service: CheckResolutionService, no_override: ChecksOverride
) -> None:
    rules = [make_check_rule("r1", category="formatting")]
    ver_cfg = ChecksVersionConfig(disabled_categories=("formatting",), disabled=(), severity_override={})

    result = service.resolve(rules, "tz", ver_cfg, no_override, no_override, no_override, no_override)

    assert result == []


def test__resolve__version_disables_specific_rule__only_that_rule_excluded(
    service: CheckResolutionService, no_override: ChecksOverride
) -> None:
    rules = [make_check_rule("r1"), make_check_rule("r2")]
    ver_cfg = ChecksVersionConfig(disabled_categories=(), disabled=("r1",), severity_override={})

    result = service.resolve(rules, "tz", ver_cfg, no_override, no_override, no_override, no_override)

    ids = [r.id for r, _ in result]
    assert "r1" not in ids
    assert "r2" in ids


def test__resolve__version_severity_override__severity_changed(
    service: CheckResolutionService, no_override: ChecksOverride
) -> None:
    rules = [make_check_rule("r1", severity=CheckSeverity.warn)]
    ver_cfg = ChecksVersionConfig(disabled_categories=(), disabled=(), severity_override={"r1": CheckSeverity.err})

    result = service.resolve(rules, "tz", ver_cfg, no_override, no_override, no_override, no_override)

    assert len(result) == 1
    assert result[0][1] == CheckSeverity.err


def test__resolve__doc_definition_disables_category__rule_excluded(
    service: CheckResolutionService, empty_version_cfg: ChecksVersionConfig, no_override: ChecksOverride
) -> None:
    """Pack-author can declare per-document overrides — e.g. presentations skip formatting GOST rules."""
    rules = [make_check_rule("r1", category="formatting"), make_check_rule("r2", category="structure")]
    doc_def_checks = ChecksOverride(disabled_categories=("formatting",))

    result = service.resolve(rules, "pres", empty_version_cfg, doc_def_checks, no_override, no_override, no_override)

    ids = [r.id for r, _ in result]
    assert "r1" not in ids
    assert "r2" in ids


def test__resolve__doc_definition_disables_specific_rule__rule_excluded(
    service: CheckResolutionService, empty_version_cfg: ChecksVersionConfig, no_override: ChecksOverride
) -> None:
    rules = [make_check_rule("r1"), make_check_rule("r2")]
    doc_def_checks = ChecksOverride(disabled=("r1",))

    result = service.resolve(rules, "pres", empty_version_cfg, doc_def_checks, no_override, no_override, no_override)

    ids = [r.id for r, _ in result]
    assert "r1" not in ids
    assert "r2" in ids


def test__resolve__doc_override_disables_rule__rule_excluded(
    service: CheckResolutionService, empty_version_cfg: ChecksVersionConfig, no_override: ChecksOverride
) -> None:
    rules = [make_check_rule("r1"), make_check_rule("r2")]
    doc_override = ChecksOverride(disabled=("r1",))

    result = service.resolve(rules, "tz", empty_version_cfg, no_override, no_override, doc_override, no_override)

    ids = [r.id for r, _ in result]
    assert "r1" not in ids
    assert "r2" in ids


def test__resolve__doc_override_reenables_version_disabled_rule__rule_included(
    service: CheckResolutionService, no_override: ChecksOverride
) -> None:
    rules = [make_check_rule("r1")]
    ver_cfg = ChecksVersionConfig(disabled_categories=(), disabled=("r1",), severity_override={})
    doc_override = ChecksOverride(enabled=("r1",))

    result = service.resolve(rules, "tz", ver_cfg, no_override, no_override, doc_override, no_override)

    ids = [r.id for r, _ in result]
    assert "r1" in ids


def test__resolve__user_override_disables_rule__rule_excluded(
    service: CheckResolutionService, empty_version_cfg: ChecksVersionConfig, no_override: ChecksOverride
) -> None:
    rules = [make_check_rule("r1"), make_check_rule("r2")]
    user_override = ChecksOverride(disabled=("r2",))

    result = service.resolve(rules, "tz", empty_version_cfg, no_override, no_override, no_override, user_override)

    ids = [r.id for r, _ in result]
    assert "r2" not in ids
    assert "r1" in ids


def test__resolve__project_override_disables_rule__rule_excluded(
    service: CheckResolutionService, empty_version_cfg: ChecksVersionConfig, no_override: ChecksOverride
) -> None:
    rules = [make_check_rule("r1"), make_check_rule("r2")]
    project_override = ChecksOverride(disabled=("r1",))

    result = service.resolve(rules, "tz", empty_version_cfg, no_override, project_override, no_override, no_override)

    ids = [r.id for r, _ in result]
    assert "r1" not in ids
    assert "r2" in ids


def test__resolve__doc_override_reenables_project_disabled_rule__doc_wins(
    service: CheckResolutionService, empty_version_cfg: ChecksVersionConfig, no_override: ChecksOverride
) -> None:
    """Project disables r1; doc force-enables it via `enabled`. Doc wins."""
    rules = [make_check_rule("r1")]
    project_override = ChecksOverride(disabled=("r1",))
    doc_override = ChecksOverride(enabled=("r1",))

    result = service.resolve(rules, "tz", empty_version_cfg, no_override, project_override, doc_override, no_override)

    ids = [r.id for r, _ in result]
    assert "r1" in ids


def test__resolve__project_override_reenables_doc_definition_disabled_rule__project_wins(
    service: CheckResolutionService, empty_version_cfg: ChecksVersionConfig, no_override: ChecksOverride
) -> None:
    """Pack author disables a category for the document; project re-enables a specific rule from that category."""
    rules = [make_check_rule("r1", category="formatting")]
    doc_def_checks = ChecksOverride(disabled_categories=("formatting",))
    project_override = ChecksOverride(enabled=("r1",))

    result = service.resolve(
        rules, "pres", empty_version_cfg, doc_def_checks, project_override, no_override, no_override
    )

    ids = [r.id for r, _ in result]
    assert "r1" in ids


def test__resolve__doc_severity_override_wins_over_project__severity_from_doc(
    service: CheckResolutionService, empty_version_cfg: ChecksVersionConfig, no_override: ChecksOverride
) -> None:
    rules = [make_check_rule("r1", severity=CheckSeverity.warn)]
    project_override = ChecksOverride(severity_override={"r1": CheckSeverity.err})
    doc_override = ChecksOverride(severity_override={"r1": CheckSeverity.info})

    result = service.resolve(rules, "tz", empty_version_cfg, no_override, project_override, doc_override, no_override)

    assert len(result) == 1
    assert result[0][1] == CheckSeverity.info


def test__resolve__no_rules__returns_empty_list(
    service: CheckResolutionService, empty_version_cfg: ChecksVersionConfig, no_override: ChecksOverride
) -> None:
    result = service.resolve([], "tz", empty_version_cfg, no_override, no_override, no_override, no_override)

    assert result == []


def test__resolve__severity_cascade_version_doc_user__user_wins(
    service: CheckResolutionService, empty_version_cfg: ChecksVersionConfig, no_override: ChecksOverride
) -> None:
    """version sets err, doc overrides to info, user overrides to warn."""
    rules = [make_check_rule("r1", severity=CheckSeverity.warn)]
    ver_cfg = ChecksVersionConfig(disabled_categories=(), disabled=(), severity_override={"r1": CheckSeverity.err})
    doc_override = ChecksOverride(severity_override={"r1": CheckSeverity.info})
    user_override = ChecksOverride(severity_override={"r1": CheckSeverity.warn})

    result = service.resolve(rules, "tz", ver_cfg, no_override, no_override, doc_override, user_override)

    assert len(result) == 1
    assert result[0][1] == CheckSeverity.warn
