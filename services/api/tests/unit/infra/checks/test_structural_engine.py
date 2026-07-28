from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.core.enums import CheckEngine, CheckSeverity
from hse_doc_studio.infra.checks.structural_engine import StructuralCheckEngine

from tests.factories import make_check_rule

engine = StructuralCheckEngine()


def _tex(folder: Path, filename: str, content: str) -> None:
    (folder / filename).write_text(content, encoding="utf-8")


@pytest.mark.unit
def test__structural_engine__required_command_present__no_results(tmp_path: Path) -> None:
    _tex(tmp_path, "main.tex", r"\author{Ivan}")
    rule = make_check_rule(
        rule_id="s1",
        engine=CheckEngine.structural,
        params={"required_commands": [r"\author"], "files": "*.tex"},
    )
    assert engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None) == []


@pytest.mark.unit
def test__structural_engine__required_command_missing__returns_result(tmp_path: Path) -> None:
    _tex(tmp_path, "main.tex", r"\title{Title}")
    rule = make_check_rule(
        rule_id="s1",
        engine=CheckEngine.structural,
        params={"required_commands": [r"\author"], "files": "*.tex"},
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1
    assert r"\author" in results[0].message


@pytest.mark.unit
def test__structural_engine__multiple_required_commands_one_missing__returns_one_result(tmp_path: Path) -> None:
    _tex(tmp_path, "main.tex", r"\author{Ivan}" + "\n" + r"\date{2026}")
    rule = make_check_rule(
        rule_id="s1",
        engine=CheckEngine.structural,
        params={"required_commands": [r"\author", r"\title"], "files": "*.tex"},
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1
    assert r"\title" in results[0].message


@pytest.mark.unit
def test__structural_engine__min_sections_met__no_results(tmp_path: Path) -> None:
    _tex(tmp_path, "main.tex", r"\section{A}" + "\n" + r"\section{B}" + "\n" + r"\section{C}")
    rule = make_check_rule(
        rule_id="s2",
        engine=CheckEngine.structural,
        params={"min_sections": 3, "files": "*.tex"},
    )
    assert engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None) == []


# ──────────────────────────────────────────────────────────────────────────
# float_orphans — every figure/table must carry a \label and be referenced
# ──────────────────────────────────────────────────────────────────────────


def _float_rule() -> object:
    return make_check_rule(
        rule_id="gost/float-orphans",
        engine=CheckEngine.structural,
        params={"check": "float_orphans"},
    )


@pytest.mark.unit
def test__float_orphans__figure_labeled_and_referenced__no_results(tmp_path: Path) -> None:
    _tex(
        tmp_path,
        "vkr.tex",
        "\\begin{figure}\n\\caption{Схема}\n\\label{fig:arch}\n\\end{figure}\n"
        "Как показано на рис.~\\ref{fig:arch}, всё хорошо.",
    )
    assert engine.run(_float_rule(), CheckSeverity.warn, tmp_path, "vkr", "vkr.tex", None) == []


@pytest.mark.unit
def test__float_orphans__figure_labeled_but_unreferenced__fires(tmp_path: Path) -> None:
    _tex(tmp_path, "vkr.tex", "\\begin{figure}\n\\caption{C}\n\\label{fig:x}\n\\end{figure}")
    results = engine.run(_float_rule(), CheckSeverity.warn, tmp_path, "vkr", "vkr.tex", None)
    assert len(results) == 1
    assert "fig:x" in results[0].message
    assert results[0].location is not None
    assert results[0].location.line == 1


@pytest.mark.unit
def test__float_orphans__figure_without_label__fires(tmp_path: Path) -> None:
    _tex(tmp_path, "vkr.tex", "\\begin{figure}\n\\caption{Без метки}\n\\end{figure}")
    results = engine.run(_float_rule(), CheckSeverity.warn, tmp_path, "vkr", "vkr.tex", None)
    assert len(results) == 1
    assert "label" in results[0].message.lower()


@pytest.mark.unit
def test__float_orphans__table_unreferenced__fires_with_table_wording(tmp_path: Path) -> None:
    _tex(tmp_path, "vkr.tex", "\\begin{table}\n\\caption{Данные}\n\\label{tab:y}\n\\end{table}")
    results = engine.run(_float_rule(), CheckSeverity.warn, tmp_path, "vkr", "vkr.tex", None)
    assert len(results) == 1
    assert "таблиц" in results[0].message.lower()


@pytest.mark.unit
def test__float_orphans__reference_in_included_file__satisfies(tmp_path: Path) -> None:
    (tmp_path / "chapters").mkdir()
    _tex(tmp_path / "chapters", "body.tex", "Видно на \\autoref{fig:arch}.")
    _tex(
        tmp_path,
        "vkr.tex",
        "\\begin{figure}\n\\label{fig:arch}\n\\end{figure}\n\\input{chapters/body}",
    )
    assert engine.run(_float_rule(), CheckSeverity.warn, tmp_path, "vkr", "vkr.tex", None) == []


@pytest.mark.unit
def test__float_orphans__starred_figure_referenced__no_results(tmp_path: Path) -> None:
    _tex(
        tmp_path,
        "vkr.tex",
        "\\begin{figure*}\n\\label{fig:wide}\n\\end{figure*}\nСм. \\cref{fig:wide}.",
    )
    assert engine.run(_float_rule(), CheckSeverity.warn, tmp_path, "vkr", "vkr.tex", None) == []


@pytest.mark.unit
def test__structural_engine__min_sections_not_met__returns_result(tmp_path: Path) -> None:
    _tex(tmp_path, "main.tex", r"\section{A}")
    rule = make_check_rule(
        rule_id="s2",
        engine=CheckEngine.structural,
        params={"min_sections": 3, "files": "*.tex"},
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1
    assert "1" in results[0].message
    assert "3" in results[0].message


@pytest.mark.unit
def test__structural_engine__max_sections_not_exceeded__no_results(tmp_path: Path) -> None:
    _tex(tmp_path, "main.tex", r"\section{A}" + "\n" + r"\section{B}")
    rule = make_check_rule(
        rule_id="s3",
        engine=CheckEngine.structural,
        params={"max_sections": 5, "files": "*.tex"},
    )
    assert engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None) == []


@pytest.mark.unit
def test__structural_engine__max_sections_exceeded__returns_result(tmp_path: Path) -> None:
    content = "\n".join(rf"\section{{{i}}}" for i in range(6))
    _tex(tmp_path, "main.tex", content)
    rule = make_check_rule(
        rule_id="s3",
        engine=CheckEngine.structural,
        params={"max_sections": 3, "files": "*.tex"},
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1
    assert "6" in results[0].message
    assert "3" in results[0].message


@pytest.mark.unit
def test__structural_engine__no_matching_files_no_checks__no_results(tmp_path: Path) -> None:
    rule = make_check_rule(
        rule_id="s4",
        engine=CheckEngine.structural,
        params={"required_commands": [], "files": "*.tex"},
    )
    assert engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None) == []


@pytest.mark.unit
def test__structural_engine__no_matching_files_with_required_cmd__reports_missing(tmp_path: Path) -> None:
    rule = make_check_rule(
        rule_id="s4b",
        engine=CheckEngine.structural,
        params={"required_commands": [r"\author"], "files": "*.tex"},
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1
    assert r"\author" in results[0].message


@pytest.mark.unit
def test__structural_engine__empty_params__no_results(tmp_path: Path) -> None:
    _tex(tmp_path, "main.tex", r"\title{X}")
    rule = make_check_rule(rule_id="s5", engine=CheckEngine.structural, params={})
    assert engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None) == []


@pytest.mark.unit
def test__structural_engine__doc_subdir_exists__searches_subdir_and_common(tmp_path: Path) -> None:
    # Legacy mode (no `check` key) falls back to match_files(glob) first,
    # then to (<doc_id>/ + common/) if the glob matches nothing. With
    # `files: "*.tex"` here, match_files finds only top-level root.tex.
    subdir = tmp_path / "doc1"
    subdir.mkdir()
    _tex(subdir, "main.tex", r"\title{X}")
    _tex(tmp_path, "root.tex", r"\author{Someone}")
    rule = make_check_rule(
        rule_id="s6",
        engine=CheckEngine.structural,
        params={"required_commands": [r"\author"], "files": "*.tex"},
    )
    # `\author` IS present in root.tex, which the top-level glob picks up —
    # no diagnostic expected.
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert results == []


# ──────────────────────────────────────────────────────────────────────────
# Preamble properties are read from the document as it is actually compiled —
# the main .tex with its \input chain inlined — never from a sibling .tex the
# document doesn't include (an alternative variant with its own preamble).
# ──────────────────────────────────────────────────────────────────────────

_ESPD_GEOMETRY = r"\usepackage[a4paper,left=20mm,right=10mm,top=25mm,bottom=40mm]{geometry}"
_SRS_GEOMETRY = r"\usepackage[a4paper,left=25mm,right=15mm,top=20mm,bottom=20mm]{geometry}"
_TZ_SOURCE = "technical_specification/technical_specification.tex"


def _geometry_rule() -> object:
    return make_check_rule(
        rule_id="gost-19.201-78/page-margins",
        engine=CheckEngine.structural,
        params={
            "check": "page_geometry",
            "expected": {"left_mm": 20, "right_mm": 10, "top_mm": 25, "bottom_mm": 40},
            "tolerance_mm": 2,
        },
    )


def _espd_doc(tmp_path: Path, preamble: str) -> None:
    """A ЕСПД document: main .tex in its own folder, geometry in common/preamble."""
    (tmp_path / "common").mkdir()
    _tex(tmp_path / "common", "preamble.tex", preamble)
    doc_dir = tmp_path / "technical_specification"
    doc_dir.mkdir()
    _tex(
        doc_dir,
        "technical_specification.tex",
        "\\input{../common/preamble}\n\\begin{document}\nТекст\n\\end{document}",
    )


@pytest.mark.unit
def test__page_geometry__margins_from_included_preamble__no_results(tmp_path: Path) -> None:
    _espd_doc(tmp_path, _ESPD_GEOMETRY)
    assert engine.run(_geometry_rule(), CheckSeverity.info, tmp_path, "tz", _TZ_SOURCE, None) == []


@pytest.mark.unit
def test__page_geometry__sibling_variant_with_own_geometry__is_not_measured(tmp_path: Path) -> None:
    _espd_doc(tmp_path, _ESPD_GEOMETRY)
    # Sorts before technical_specification.tex, so a folder-wide scan would
    # measure this alternative variant instead of the compiled document.
    _tex(tmp_path / "technical_specification", "srs_29148.tex", _SRS_GEOMETRY)

    assert engine.run(_geometry_rule(), CheckSeverity.info, tmp_path, "tz", _TZ_SOURCE, None) == []


@pytest.mark.unit
def test__page_geometry__included_preamble_violates__fires(tmp_path: Path) -> None:
    _espd_doc(tmp_path, _SRS_GEOMETRY)

    results = engine.run(_geometry_rule(), CheckSeverity.info, tmp_path, "tz", _TZ_SOURCE, None)

    assert len(results) == 1
    assert "left=25.0" in results[0].message


@pytest.mark.unit
def test__line_spacing__sibling_variant_holds_expected_spacing__still_fires(tmp_path: Path) -> None:
    _espd_doc(tmp_path, _ESPD_GEOMETRY + "\n" + r"\linespread{2.0}")
    _tex(tmp_path / "technical_specification", "srs_29148.tex", r"\linespread{1.5}")
    rule = make_check_rule(
        rule_id="gost-19.201-78/line-spacing",
        engine=CheckEngine.structural,
        params={"check": "line_spacing", "expected": 1.5},
    )

    results = engine.run(rule, CheckSeverity.warn, tmp_path, "tz", _TZ_SOURCE, None)

    assert len(results) == 1
    assert "2.0" in results[0].message


@pytest.mark.unit
def test__structural_engine__min_and_max_both_violated__returns_two_results(tmp_path: Path) -> None:
    _tex(tmp_path, "main.tex", r"\section{A}")
    rule = make_check_rule(
        rule_id="s7",
        engine=CheckEngine.structural,
        params={"min_sections": 5, "max_sections": 0, "files": "*.tex"},
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 2
