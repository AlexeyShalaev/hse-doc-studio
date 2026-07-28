from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.core.enums import CheckEngine, CheckSeverity
from hse_doc_studio.infra.checks.log_parse_engine import LogParseCheckEngine

from tests.factories import make_check_rule

engine = LogParseCheckEngine()

_LATEX_ERROR_LOG = """\
This is XeLaTeX, Version 3.141592653
(./main.tex
! Undefined control sequence.
l.42 \\unknowncmd
"""

_OVERFULL_LOG = """\
This is XeLaTeX
Overfull \\hbox (12.34pt too wide) in paragraph at lines 15--20 l.15 some text here
"""

_CLEAN_LOG = "This is XeLaTeX\nAll checks passed."


def _rule(check_type: str = "errors") -> object:
    return make_check_rule(
        rule_id="log1",
        engine=CheckEngine.log_parse,
        params={"check": check_type},
    )


@pytest.mark.unit
def test__log_parse_engine__latex_error__returns_error_result() -> None:
    rule = _rule("errors")
    results = engine.run(rule, CheckSeverity.err, Path("/"), "doc1", "main.tex", _LATEX_ERROR_LOG)
    assert len(results) == 1
    assert "Ошибка LaTeX" in results[0].message
    assert results[0].location is not None
    assert results[0].location.line == 42


@pytest.mark.unit
def test__log_parse_engine__overfull_hbox__returns_overfull_result() -> None:
    rule = _rule("overfull")
    results = engine.run(rule, CheckSeverity.warn, Path("/"), "doc1", "main.tex", _OVERFULL_LOG)
    assert len(results) == 1
    assert "overfull hbox" in results[0].message.lower()
    assert results[0].location is not None
    assert results[0].location.line == 15


@pytest.mark.unit
def test__log_parse_engine__check_all__returns_both_errors_and_overfulls() -> None:
    combined = _LATEX_ERROR_LOG + "\n" + _OVERFULL_LOG
    rule = _rule("all")
    results = engine.run(rule, CheckSeverity.warn, Path("/"), "doc1", "main.tex", combined)
    messages = [r.message for r in results]
    assert any("Ошибка LaTeX" in m for m in messages)
    assert any("overfull hbox" in m.lower() for m in messages)


@pytest.mark.unit
def test__log_parse_engine__clean_log__no_results() -> None:
    rule = _rule("all")
    results = engine.run(rule, CheckSeverity.warn, Path("/"), "doc1", "main.tex", _CLEAN_LOG)
    assert results == []


@pytest.mark.unit
@pytest.mark.parametrize(
    ("check_type", "log"),
    [("errors", _OVERFULL_LOG), ("overfull", _LATEX_ERROR_LOG)],
)
def test__log_parse_engine__check_type_does_not_match_log_content__no_results(check_type: str, log: str) -> None:
    rule = _rule(check_type)

    results = engine.run(rule, CheckSeverity.warn, Path("/"), "doc1", "main.tex", log)

    assert results == []


@pytest.mark.unit
def test__log_parse_engine__no_log_file__returns_empty(tmp_path: Path) -> None:
    rule = _rule("errors")
    results = engine.run(rule, CheckSeverity.err, tmp_path, "doc1", "main.tex", None)
    assert results == []


@pytest.mark.unit
def test__log_parse_engine__log_file_exists__reads_it(tmp_path: Path) -> None:
    log_file = tmp_path / "main.log"
    log_file.write_text(_LATEX_ERROR_LOG, encoding="utf-8")
    rule = _rule("errors")
    results = engine.run(rule, CheckSeverity.err, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1
    assert "Ошибка LaTeX" in results[0].message


@pytest.mark.unit
def test__log_parse_engine__log_content_provided__skips_file(tmp_path: Path) -> None:
    log_file = tmp_path / "main.log"
    log_file.write_text(_LATEX_ERROR_LOG, encoding="utf-8")
    rule = _rule("errors")
    results = engine.run(rule, CheckSeverity.err, tmp_path, "doc1", "main.tex", _CLEAN_LOG)
    assert results == []


@pytest.mark.unit
def test__log_parse_engine__multiple_errors_in_log__returns_all() -> None:
    log = """\
! Error one.
l.10 \\cmd
! Error two.
l.20 \\cmd2
"""
    rule = _rule("errors")
    results = engine.run(rule, CheckSeverity.err, Path("/"), "doc1", "main.tex", log)
    assert len(results) == 2
    assert results[0].location.line == 10
    assert results[1].location.line == 20


@pytest.mark.unit
def test__log_parse_engine__error_without_line_number__location_line_is_none() -> None:
    log = "! Some error without line number.\n"
    rule = _rule("errors")
    results = engine.run(rule, CheckSeverity.err, Path("/"), "doc1", "main.tex", log)
    assert len(results) == 1
    assert results[0].location is not None
    assert results[0].location.line is None
