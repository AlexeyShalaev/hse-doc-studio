from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.core.enums import CheckEngine, CheckSeverity
from hse_doc_studio.infra.checks.typography_engine import TypographyCheckEngine

from tests.factories import make_check_rule

engine = TypographyCheckEngine()


def _rule(check: str) -> object:
    return make_check_rule(
        rule_id=f"typ/{check}",
        engine=CheckEngine.typography,
        params={"check": check, "file_glob": "*.tex"},
    )


def _run(tmp_path: Path, check: str, content: str) -> list:
    (tmp_path / "main.tex").write_text(content, encoding="utf-8")
    return engine.run(_rule(check), CheckSeverity.info, tmp_path, "doc1", "main.tex", None)


@pytest.mark.unit
def test__quotes__straight_quotes_get_fix(tmp_path: Path) -> None:
    results = _run(tmp_path, "quotes", 'Это слово "важное" здесь.')
    assert len(results) == 1
    assert results[0].fix is not None
    assert results[0].fix.search == '"важное"'
    assert results[0].fix.replace == "«важное»"
    assert results[0].fix.line == 1


@pytest.mark.unit
def test__quotes__already_yolki__no_results(tmp_path: Path) -> None:
    assert _run(tmp_path, "quotes", "Слово «важное» тут.") == []


@pytest.mark.unit
def test__dash__space_hyphen_space_gets_em_dash(tmp_path: Path) -> None:
    results = _run(tmp_path, "dash", "Москва - столица России.")
    assert len(results) == 1
    assert results[0].fix.search == " - "
    assert results[0].fix.replace == " — "


@pytest.mark.unit
def test__ellipsis__three_dots(tmp_path: Path) -> None:
    results = _run(tmp_path, "ellipsis", "и так далее...")
    assert len(results) == 1
    assert results[0].fix.replace == "…"


@pytest.mark.unit
def test__initials__non_breaking_space(tmp_path: Path) -> None:
    results = _run(tmp_path, "initials", "Автор: И. И. Иванов")
    assert len(results) == 1
    assert results[0].fix.replace == "И.~И."


@pytest.mark.unit
def test__percent__non_breaking_space(tmp_path: Path) -> None:
    results = _run(tmp_path, "percent", r"Доля 10 \% от общего.")
    assert len(results) == 1
    assert results[0].fix.search == r"10 \%"
    assert results[0].fix.replace == r"10~\%"


@pytest.mark.unit
def test__percent__raw_percent_is_a_comment__no_results(tmp_path: Path) -> None:
    # A raw `%` starts a LaTeX comment — nothing typographic to fix.
    assert _run(tmp_path, "percent", "Доля 10 % от общего.") == []


@pytest.mark.unit
def test__quotes__inside_lstlisting__no_results(tmp_path: Path) -> None:
    content = "\n".join(
        [
            "\\begin{lstlisting}[language=Python]",
            'print("hello")',
            "\\end{lstlisting}",
        ]
    )
    assert _run(tmp_path, "quotes", content) == []


@pytest.mark.unit
def test__ellipsis__inside_verb_span__no_results(tmp_path: Path) -> None:
    assert _run(tmp_path, "ellipsis", r"Макрос \verb|\req{ID}{...}| описан выше.") == []


@pytest.mark.unit
def test__dash__inside_comment__no_results(tmp_path: Path) -> None:
    assert _run(tmp_path, "dash", "% черновик - убрать позже") == []


@pytest.mark.unit
def test__unknown_check__no_results(tmp_path: Path) -> None:
    assert _run(tmp_path, "bogus", 'x "y" z') == []


@pytest.mark.unit
def test__multiple_occurrences_each_reported(tmp_path: Path) -> None:
    results = _run(tmp_path, "quotes", '"a" and "b"')
    assert len(results) == 2
