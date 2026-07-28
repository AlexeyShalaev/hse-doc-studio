from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.infra.checks.utils import expand_inputs


@pytest.mark.unit
def test__single_file__lines_with_origin(tmp_path: Path) -> None:
    (tmp_path / "main.tex").write_text("a\nb\nc", encoding="utf-8")
    lines = expand_inputs(tmp_path, "main.tex")
    assert [(sl.file, sl.line, sl.text) for sl in lines] == [
        ("main.tex", 1, "a"),
        ("main.tex", 2, "b"),
        ("main.tex", 3, "c"),
    ]


@pytest.mark.unit
def test__input_is_inlined_with_real_origins(tmp_path: Path) -> None:
    (tmp_path / "chapters").mkdir()
    (tmp_path / "chapters" / "intro.tex").write_text("intro1\nintro2", encoding="utf-8")
    (tmp_path / "main.tex").write_text("before\n\\input{chapters/intro}\nafter", encoding="utf-8")
    lines = expand_inputs(tmp_path, "main.tex")
    assert [(sl.file, sl.line, sl.text) for sl in lines] == [
        ("main.tex", 1, "before"),
        ("chapters/intro.tex", 1, "intro1"),
        ("chapters/intro.tex", 2, "intro2"),
        ("main.tex", 3, "after"),
    ]


@pytest.mark.unit
def test__include_without_extension_resolves(tmp_path: Path) -> None:
    (tmp_path / "body.tex").write_text("X", encoding="utf-8")
    (tmp_path / "main.tex").write_text("\\include{body}", encoding="utf-8")
    lines = expand_inputs(tmp_path, "main.tex")
    assert [(sl.file, sl.text) for sl in lines] == [("body.tex", "X")]


@pytest.mark.unit
def test__commented_input_is_not_expanded(tmp_path: Path) -> None:
    (tmp_path / "secret.tex").write_text("HIDDEN", encoding="utf-8")
    (tmp_path / "main.tex").write_text("% \\input{secret}", encoding="utf-8")
    lines = expand_inputs(tmp_path, "main.tex")
    assert [sl.text for sl in lines] == ["% \\input{secret}"]
    assert all("HIDDEN" not in sl.text for sl in lines)


@pytest.mark.unit
def test__missing_include_left_as_literal(tmp_path: Path) -> None:
    (tmp_path / "main.tex").write_text("\\input{nope}", encoding="utf-8")
    lines = expand_inputs(tmp_path, "main.tex")
    assert [sl.text for sl in lines] == ["\\input{nope}"]


@pytest.mark.unit
def test__cycle_does_not_loop(tmp_path: Path) -> None:
    (tmp_path / "a.tex").write_text("A\n\\input{b}", encoding="utf-8")
    (tmp_path / "b.tex").write_text("B\n\\input{a}", encoding="utf-8")
    lines = expand_inputs(tmp_path, "a.tex")
    texts = [sl.text for sl in lines]
    assert "A" in texts
    assert "B" in texts
    # 'a' is visited once; the back-reference to it is dropped, no infinite loop.
    assert texts.count("A") == 1


@pytest.mark.unit
def test__input_relative_to_including_file_dir(tmp_path: Path) -> None:
    (tmp_path / "parts").mkdir()
    (tmp_path / "parts" / "ch.tex").write_text("\\input{sub}", encoding="utf-8")
    (tmp_path / "parts" / "sub.tex").write_text("DEEP", encoding="utf-8")
    (tmp_path / "main.tex").write_text("\\input{parts/ch}", encoding="utf-8")
    lines = expand_inputs(tmp_path, "main.tex")
    assert [(sl.file, sl.text) for sl in lines] == [("parts/sub.tex", "DEEP")]
