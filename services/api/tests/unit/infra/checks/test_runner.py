from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from hse_doc_studio.core.enums import CheckEngine, CheckSeverity
from hse_doc_studio.infra.checks.runner import CheckRunner

from tests.factories import make_check_rule


def _make_runner() -> CheckRunner:
    return CheckRunner(lt_manager=MagicMock(), lt_client=MagicMock())


@pytest.mark.unit
@pytest.mark.parametrize(
    "engine",
    [
        CheckEngine.regex,
        CheckEngine.structural,
        CheckEngine.tex_command_count,
        CheckEngine.reference_check,
        CheckEngine.log_parse,
        CheckEngine.python,
        CheckEngine.external,
        CheckEngine.typography,
    ],
)
def test__run_all__custom_mode__suppressed_engines_return_skipped(tmp_path: Path, engine: CheckEngine) -> None:
    runner = _make_runner()
    rule = make_check_rule(rule_id="r1", engine=engine)

    results = runner.run_all(
        rules_with_severity=[(rule, CheckSeverity.warn)],
        project_folder=tmp_path,
        doc_id="tz",
        source_file="tz/_custom/file.docx",
        custom_mode=True,
    )

    assert len(results) == 1
    assert results[0].rule_id == "r1"
    assert results[0].severity == CheckSeverity.skipped


@pytest.mark.unit
def test__run_all__custom_mode__file_exists_engine_still_runs(tmp_path: Path) -> None:
    runner = _make_runner()
    # file_exists checks for a required file that is NOT present — should
    # still produce a real (non-skipped) finding even in custom_mode.
    rule = make_check_rule(rule_id="fe", engine=CheckEngine.file_exists, params={"path": "missing.txt"})

    results = runner.run_all(
        rules_with_severity=[(rule, CheckSeverity.err)],
        project_folder=tmp_path,
        doc_id="tz",
        source_file="tz/_custom/file.docx",
        custom_mode=True,
    )

    assert len(results) == 1
    assert results[0].severity == CheckSeverity.err
    assert results[0].rule_id == "fe"


@pytest.mark.unit
def test__run_all__custom_mode_false__suppressed_engines_run_normally(tmp_path: Path) -> None:
    runner = _make_runner()
    (tmp_path / "main.tex").write_text(r"\todo{fix}", encoding="utf-8")
    rule = make_check_rule(
        rule_id="r1",
        engine=CheckEngine.regex,
        params={"pattern": r"\\todo\{", "file_glob": "*.tex", "negate": True},
    )

    results = runner.run_all(
        rules_with_severity=[(rule, CheckSeverity.warn)],
        project_folder=tmp_path,
        doc_id="doc1",
        source_file="main.tex",
        custom_mode=False,
    )

    assert len(results) == 1
    assert results[0].severity == CheckSeverity.warn


@pytest.mark.unit
def test__run_all__skipped_results_not_counted_as_error_or_warning(tmp_path: Path) -> None:
    runner = _make_runner()
    rules = [
        (make_check_rule(rule_id="r1", engine=CheckEngine.regex), CheckSeverity.err),
        (make_check_rule(rule_id="r2", engine=CheckEngine.file_exists, params={"path": "x.txt"}), CheckSeverity.warn),
    ]

    results = runner.run_all(
        rules_with_severity=rules,
        project_folder=tmp_path,
        doc_id="tz",
        source_file="tz/_custom/file.docx",
        custom_mode=True,
    )

    has_errors = any(r.severity == CheckSeverity.err for r in results)
    has_warnings = any(r.severity == CheckSeverity.warn for r in results)
    # r1 (regex) is suppressed -> skipped, not an error. r2 (file_exists) is a
    # real finding since "x.txt" doesn't exist -> a genuine warning.
    assert has_errors is False
    assert has_warnings is True
    assert any(r.severity == CheckSeverity.skipped for r in results)
