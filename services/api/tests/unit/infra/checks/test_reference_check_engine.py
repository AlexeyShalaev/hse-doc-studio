from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.core.enums import CheckEngine, CheckSeverity
from hse_doc_studio.infra.checks.reference_check_engine import ReferenceCheckEngine

from tests.factories import make_check_rule

engine = ReferenceCheckEngine()


def _write(folder: Path, name: str, content: str) -> None:
    target = folder / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────
# Mode "refs"
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test__refs__all_refs_resolved__no_results(tmp_path: Path) -> None:
    _write(tmp_path, "main.tex", r"\label{sec:intro}" + "\n" + r"See \ref{sec:intro}.")
    rule = make_check_rule(
        rule_id="ref-ok",
        engine=CheckEngine.reference_check,
        params={"mode": "refs"},
    )
    assert engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None) == []


@pytest.mark.unit
def test__refs__dangling_ref__reports_with_location(tmp_path: Path) -> None:
    _write(tmp_path, "main.tex", "first\n" + r"See \ref{sec:missing}." + "\n")
    rule = make_check_rule(
        rule_id="ref-broken",
        engine=CheckEngine.reference_check,
        params={"mode": "refs"},
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1
    assert results[0].location.file == "main.tex"
    assert results[0].location.line == 2
    assert "sec:missing" in results[0].message


@pytest.mark.unit
def test__refs__multiple_dangling_refs__deduplicates_by_key(tmp_path: Path) -> None:
    content = (
        r"\ref{a}" + "\n" + r"\ref{b}" + "\n" + r"\ref{a}" + "\n"  # duplicate of a
    )
    _write(tmp_path, "main.tex", content)
    rule = make_check_rule(
        rule_id="ref-dup",
        engine=CheckEngine.reference_check,
        params={"mode": "refs"},
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 2
    messages = " ".join(r.message for r in results)
    assert "{a}" in messages
    assert "{b}" in messages


@pytest.mark.unit
def test__refs__cross_file__labels_in_one_file_refs_in_another(tmp_path: Path) -> None:
    _write(tmp_path, "intro.tex", r"\label{sec:intro}")
    _write(tmp_path, "main.tex", r"See \ref{sec:intro}.")
    rule = make_check_rule(
        rule_id="ref-cross",
        engine=CheckEngine.reference_check,
        params={"mode": "refs"},
    )
    assert engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None) == []


@pytest.mark.unit
def test__refs__accepts_autoref_eqref_pageref(tmp_path: Path) -> None:
    content = (
        r"\label{eq:1}" + "\n" + r"\eqref{eq:1}" + "\n" + r"\autoref{eq:missing}" + "\n"  # broken
    )
    _write(tmp_path, "main.tex", content)
    rule = make_check_rule(
        rule_id="ref-aliases",
        engine=CheckEngine.reference_check,
        params={"mode": "refs"},
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1
    assert "eq:missing" in results[0].message


@pytest.mark.unit
def test__refs__empty_project__no_results(tmp_path: Path) -> None:
    rule = make_check_rule(
        rule_id="ref-empty",
        engine=CheckEngine.reference_check,
        params={"mode": "refs"},
    )
    assert engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None) == []


# ──────────────────────────────────────────────────────────────────────────
# Mode "cites"
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test__cites__cite_resolved_in_bib__no_results(tmp_path: Path) -> None:
    _write(tmp_path, "refs.bib", "@article{key1, title={X}}")
    _write(tmp_path, "main.tex", r"\cite{key1}")
    rule = make_check_rule(
        rule_id="cite-ok",
        engine=CheckEngine.reference_check,
        params={"mode": "cites"},
    )
    assert engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None) == []


@pytest.mark.unit
def test__cites__cite_not_in_bib__reports(tmp_path: Path) -> None:
    _write(tmp_path, "refs.bib", "@article{key1, title={X}}")
    _write(tmp_path, "main.tex", r"\cite{missingkey}")
    rule = make_check_rule(
        rule_id="cite-broken",
        engine=CheckEngine.reference_check,
        params={"mode": "cites"},
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1
    assert "missingkey" in results[0].message


@pytest.mark.unit
def test__cites__multiple_keys_in_one_cite__validates_each(tmp_path: Path) -> None:
    _write(tmp_path, "refs.bib", "@book{a, x={1}}\n@book{b, x={2}}")
    _write(tmp_path, "main.tex", r"\cite{a, b, c, d}")
    rule = make_check_rule(
        rule_id="cite-multi",
        engine=CheckEngine.reference_check,
        params={"mode": "cites"},
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 2
    messages = " ".join(r.message for r in results)
    assert "{c}" in messages
    assert "{d}" in messages


@pytest.mark.unit
def test__cites__variants_citep_citet_nocite(tmp_path: Path) -> None:
    _write(tmp_path, "refs.bib", "@book{a, x={1}}")
    _write(tmp_path, "main.tex", r"\citep{a}\citet{a}\nocite{missing}")
    rule = make_check_rule(
        rule_id="cite-variants",
        engine=CheckEngine.reference_check,
        params={"mode": "cites"},
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1
    assert "missing" in results[0].message


@pytest.mark.unit
def test__cites__no_bib_files__every_cite_reported(tmp_path: Path) -> None:
    _write(tmp_path, "main.tex", r"\cite{anything}")
    rule = make_check_rule(
        rule_id="cite-nobib",
        engine=CheckEngine.reference_check,
        params={"mode": "cites"},
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1


# ──────────────────────────────────────────────────────────────────────────
# Misuse
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test__unknown_mode__no_results(tmp_path: Path) -> None:
    _write(tmp_path, "main.tex", r"\ref{x}")
    rule = make_check_rule(
        rule_id="bad-mode",
        engine=CheckEngine.reference_check,
        params={"mode": "garbage"},
    )
    assert engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None) == []


@pytest.mark.unit
def test__refs__localized_message_with_template(tmp_path: Path) -> None:
    _write(tmp_path, "main.tex", r"\ref{xyz}")
    rule = make_check_rule(
        rule_id="ref-template",
        engine=CheckEngine.reference_check,
        params={
            "mode": "refs",
            "message": {"ru": "Сломана ссылка: {key}"},
        },
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1
    assert results[0].message == "Сломана ссылка: xyz"


# ──────────────────────────────────────────────────────────────────────────
# Mode "unused" — bib entries never cited in the text
# ──────────────────────────────────────────────────────────────────────────


def _unused_rule() -> object:
    return make_check_rule(
        rule_id="bib-unused",
        engine=CheckEngine.reference_check,
        params={"mode": "unused"},
    )


@pytest.mark.unit
def test__unused__all_sources_cited__no_results(tmp_path: Path) -> None:
    _write(tmp_path, "refs.bib", "@book{knuth, title={X}}")
    _write(tmp_path, "main.tex", r"\cite{knuth}")
    assert engine.run(_unused_rule(), CheckSeverity.info, tmp_path, "doc1", "main.tex", None) == []


@pytest.mark.unit
def test__unused__uncited_source__fires_at_bib_line(tmp_path: Path) -> None:
    _write(tmp_path, "refs.bib", "@book{used, title={A}}\n@article{orphan, title={B}}")
    _write(tmp_path, "main.tex", r"\cite{used}")
    results = engine.run(_unused_rule(), CheckSeverity.info, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1
    assert "orphan" in results[0].message
    assert results[0].location is not None
    assert results[0].location.line == 2
    assert results[0].location.file == "refs.bib"


@pytest.mark.unit
def test__unused__multi_key_cite_counts_all(tmp_path: Path) -> None:
    _write(tmp_path, "refs.bib", "@book{a, title={A}}\n@book{b, title={B}}")
    _write(tmp_path, "main.tex", r"\cite{a,b}")
    assert engine.run(_unused_rule(), CheckSeverity.info, tmp_path, "doc1", "main.tex", None) == []


@pytest.mark.unit
def test__unused__no_bib_files__no_results(tmp_path: Path) -> None:
    _write(tmp_path, "main.tex", r"\cite{x}")
    assert engine.run(_unused_rule(), CheckSeverity.info, tmp_path, "doc1", "main.tex", None) == []


# ──────────────────────────────────────────────────────────────────────────
# Masking: \verb spans, comments, listings; package labels; option labels
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test__refs__package_label_lastpage__no_results(tmp_path: Path) -> None:
    _write(tmp_path, "main.tex", "Listov \\pageref{LastPage}\n")
    rule = make_check_rule(
        rule_id="ref-lastpage",
        engine=CheckEngine.reference_check,
        params={"mode": "refs"},
    )
    assert engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None) == []


@pytest.mark.unit
def test__refs__ref_inside_verb_span__ignored(tmp_path: Path) -> None:
    _write(tmp_path, "main.tex", "Primer: \\verb|\\ref{fig:arch}| v tekste.\n")
    rule = make_check_rule(
        rule_id="ref-verb",
        engine=CheckEngine.reference_check,
        params={"mode": "refs"},
    )
    assert engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None) == []


@pytest.mark.unit
def test__refs__ref_inside_comment__ignored(tmp_path: Path) -> None:
    _write(tmp_path, "main.tex", "text\n% see \\ref{sec:draft}\n")
    rule = make_check_rule(
        rule_id="ref-comment",
        engine=CheckEngine.reference_check,
        params={"mode": "refs"},
    )
    assert engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None) == []


@pytest.mark.unit
def test__refs__lstlisting_option_label__resolves(tmp_path: Path) -> None:
    content = (
        "sm. listing~\\ref{lst:example}\n"
        "\\begin{lstlisting}[language=Python, caption={Primer}, label={lst:example}]\n"
        "print('x')\n"
        "\\end{lstlisting}\n"
    )
    _write(tmp_path, "main.tex", content)
    rule = make_check_rule(
        rule_id="ref-lst-label",
        engine=CheckEngine.reference_check,
        params={"mode": "refs"},
    )
    assert engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None) == []


@pytest.mark.unit
def test__cites__cite_inside_verb_span__ignored(tmp_path: Path) -> None:
    _write(tmp_path, "main.tex", "Primer: \\verb|\\cite{gost}| v tekste.\n")
    rule = make_check_rule(
        rule_id="cite-verb",
        engine=CheckEngine.reference_check,
        params={"mode": "cites"},
    )
    assert engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None) == []
