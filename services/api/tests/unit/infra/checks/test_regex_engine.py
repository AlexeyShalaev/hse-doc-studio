from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.core.enums import CheckEngine, CheckSeverity
from hse_doc_studio.infra.checks.regex_engine import RegexCheckEngine

from tests.factories import make_check_rule

engine = RegexCheckEngine()


# ──────────────────────────────────────────────────────────────────────────
# negate: true — forbidden pattern, fire per match
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test__regex_engine__negate__pattern_found_in_file__returns_result_with_line(tmp_path: Path) -> None:
    (tmp_path / "main.tex").write_text(r"\todo{fix this}", encoding="utf-8")
    rule = make_check_rule(
        rule_id="r1",
        engine=CheckEngine.regex,
        params={
            "pattern": r"\\todo\{",
            "file_glob": "*.tex",
            "negate": True,
            "message": "TODO найден",
        },
        title={"ru": "TODO найден"},
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1
    assert results[0].location is not None
    assert results[0].location.line == 1
    assert results[0].message == "TODO найден"
    assert results[0].rule_id == "r1"


@pytest.mark.unit
def test__regex_engine__negate__pattern_not_found__no_results(tmp_path: Path) -> None:
    (tmp_path / "main.tex").write_text(r"\section{Clean}", encoding="utf-8")
    rule = make_check_rule(
        rule_id="r1",
        engine=CheckEngine.regex,
        params={"pattern": r"\\todo\{", "file_glob": "*.tex", "negate": True},
    )
    assert engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None) == []


@pytest.mark.unit
def test__regex_engine__negate__multiple_matches_in_file__returns_all(tmp_path: Path) -> None:
    content = r"\todo{a}" + "\n" + r"\todo{b}" + "\n" + r"\done{c}"
    (tmp_path / "main.tex").write_text(content, encoding="utf-8")
    rule = make_check_rule(
        rule_id="r1",
        engine=CheckEngine.regex,
        params={"pattern": r"\\todo", "file_glob": "*.tex", "negate": True},
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 2
    assert results[0].location.line == 1
    assert results[1].location.line == 2


@pytest.mark.unit
def test__regex_engine__negate__multiple_files__searches_all(tmp_path: Path) -> None:
    (tmp_path / "a.tex").write_text(r"\todo{in a}", encoding="utf-8")
    (tmp_path / "b.tex").write_text(r"\todo{in b}", encoding="utf-8")
    (tmp_path / "c.tex").write_text(r"\section{clean}", encoding="utf-8")
    rule = make_check_rule(
        rule_id="r1",
        engine=CheckEngine.regex,
        params={"pattern": r"\\todo", "file_glob": "*.tex", "negate": True},
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 2


@pytest.mark.unit
def test__regex_engine__negate__relative_path_in_location(tmp_path: Path) -> None:
    (tmp_path / "main.tex").write_text(r"\todo{fix}", encoding="utf-8")
    rule = make_check_rule(
        rule_id="r1",
        engine=CheckEngine.regex,
        params={"pattern": r"\\todo", "file_glob": "*.tex", "negate": True},
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1
    assert not results[0].location.file.startswith("/")
    assert "main.tex" in results[0].location.file


# ──────────────────────────────────────────────────────────────────────────
# negate: false (default) — required pattern, fire when missing
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test__regex_engine__required__pattern_present__no_results(tmp_path: Path) -> None:
    (tmp_path / "main.tex").write_text(r"\section{Введение}", encoding="utf-8")
    rule = make_check_rule(
        rule_id="r-intro",
        engine=CheckEngine.regex,
        params={
            "pattern": r"\\section\*?\{[^}]*[Вв]ведени",
            "file_glob": "*.tex",
            "message": "Не найден раздел Введение",
        },
    )
    assert engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None) == []


@pytest.mark.unit
def test__regex_engine__required__pattern_missing__fires_with_yaml_message(tmp_path: Path) -> None:
    (tmp_path / "main.tex").write_text(r"\section{Заключение}", encoding="utf-8")
    rule = make_check_rule(
        rule_id="r-intro",
        engine=CheckEngine.regex,
        params={
            "pattern": r"\\section\*?\{[^}]*[Вв]ведени",
            "file_glob": "*.tex",
            "message": "Не найден раздел Введение",
        },
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1
    assert results[0].message == "Не найден раздел Введение"
    assert results[0].location.line is None


@pytest.mark.unit
def test__regex_engine__required__localized_message_picks_ru(tmp_path: Path) -> None:
    (tmp_path / "main.tex").write_text("nothing", encoding="utf-8")
    rule = make_check_rule(
        rule_id="r-loc",
        engine=CheckEngine.regex,
        params={
            "pattern": r"\\bibliography",
            "file_glob": "*.tex",
            "message": {"ru": "Нет библиографии", "en": "Missing bibliography"},
        },
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1
    assert results[0].message == "Нет библиографии"


@pytest.mark.unit
def test__regex_engine__required__no_files__falls_back_to_source_file(tmp_path: Path) -> None:
    rule = make_check_rule(
        rule_id="r1",
        engine=CheckEngine.regex,
        params={"pattern": r"\\section", "file_glob": "*.tex", "message": "X"},
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1
    assert results[0].location.file == "main.tex"


# ──────────────────────────────────────────────────────────────────────────
# Misuse / edge cases
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test__regex_engine__no_pattern_in_rule__no_results(tmp_path: Path) -> None:
    (tmp_path / "main.tex").write_text(r"\todo{fix}", encoding="utf-8")
    rule = make_check_rule(
        rule_id="r1",
        engine=CheckEngine.regex,
        params={"file_glob": "*.tex"},
    )
    assert engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None) == []


@pytest.mark.unit
def test__regex_engine__invalid_regex_pattern__no_results(tmp_path: Path) -> None:
    (tmp_path / "main.tex").write_text(r"\todo{fix}", encoding="utf-8")
    rule = make_check_rule(
        rule_id="r1",
        engine=CheckEngine.regex,
        params={"pattern": "[invalid(", "file_glob": "*.tex"},
    )
    assert engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None) == []


# ──────────────────────────────────────────────────────────────────────────
# flags — honored when compiling the pattern (regression: previously dropped)
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test__regex_engine__no_flag__case_sensitive_by_default(tmp_path: Path) -> None:
    (tmp_path / "main.tex").write_text(r"\TODO{fix}", encoding="utf-8")
    rule = make_check_rule(
        rule_id="r1",
        engine=CheckEngine.regex,
        params={"pattern": r"\\todo", "file_glob": "*.tex", "negate": True},
    )
    assert engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None) == []


@pytest.mark.unit
def test__regex_engine__ignorecase_flag__matches_other_case(tmp_path: Path) -> None:
    (tmp_path / "main.tex").write_text(r"\TODO{fix}", encoding="utf-8")
    rule = make_check_rule(
        rule_id="r1",
        engine=CheckEngine.regex,
        params={"pattern": r"\\todo", "file_glob": "*.tex", "negate": True, "flags": ["ignorecase"]},
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1


@pytest.mark.unit
def test__regex_engine__multiline_flag__anchors_match_each_line(tmp_path: Path) -> None:
    (tmp_path / "main.tex").write_text("intro\n\\section{Body}", encoding="utf-8")
    rule = make_check_rule(
        rule_id="r-sec",
        engine=CheckEngine.regex,
        params={"pattern": r"^\\section", "file_glob": "*.tex", "flags": ["multiline"]},
    )
    # Required pattern present on line 2 thanks to MULTILINE `^` — no diagnostic.
    assert engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None) == []


@pytest.mark.unit
def test__regex_engine__flags_as_single_string__accepted(tmp_path: Path) -> None:
    (tmp_path / "main.tex").write_text(r"\Section{X}", encoding="utf-8")
    rule = make_check_rule(
        rule_id="r1",
        engine=CheckEngine.regex,
        params={"pattern": r"\\section", "file_glob": "*.tex", "negate": True, "flags": "i"},
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1


@pytest.mark.unit
def test__regex_engine__unknown_flag__ignored_not_fatal(tmp_path: Path) -> None:
    (tmp_path / "main.tex").write_text(r"\todo{fix}", encoding="utf-8")
    rule = make_check_rule(
        rule_id="r1",
        engine=CheckEngine.regex,
        params={"pattern": r"\\todo", "file_glob": "*.tex", "negate": True, "flags": ["bogus"]},
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1
