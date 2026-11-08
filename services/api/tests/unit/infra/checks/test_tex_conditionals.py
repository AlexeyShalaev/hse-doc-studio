from __future__ import annotations

import pytest
from hse_doc_studio.infra.checks.tex_conditionals import resolve_conditionals
from hse_doc_studio.infra.checks.utils import SourceLine


def _lines(text: str, file: str = "main.tex") -> list[SourceLine]:
    return [SourceLine(file=file, line=n, text=t) for n, t in enumerate(text.split("\n"), start=1)]


def _texts(lines: list[SourceLine]) -> list[str]:
    return [sl.text for sl in resolve_conditionals(lines)]


_FLAG_OFF = "\\newif\\ifext\n\\extfalse"
_FLAG_ON = "\\newif\\ifext\n\\exttrue"
_BRANCHES = "before\n\\ifext\nON\n\\else\nOFF\n\\fi\nafter"


@pytest.mark.unit
def test__flag_false__true_branch_dropped_else_branch_kept() -> None:
    assert _texts(_lines(f"{_FLAG_OFF}\n{_BRANCHES}")) == ["\\newif\\ifext", "\\extfalse", "before", "OFF", "after"]


@pytest.mark.unit
def test__flag_true__else_branch_dropped() -> None:
    assert _texts(_lines(f"{_FLAG_ON}\n{_BRANCHES}")) == ["\\newif\\ifext", "\\exttrue", "before", "ON", "after"]


@pytest.mark.unit
def test__kept_lines_keep_their_origin() -> None:
    meta = _lines(_FLAG_OFF, file="common/meta.tex")
    body = _lines(_BRANCHES, file="doc/doc.tex")

    kept = resolve_conditionals(meta + body)

    assert [(sl.file, sl.line) for sl in kept if sl.file == "doc/doc.tex"] == [
        ("doc/doc.tex", 1),
        ("doc/doc.tex", 5),
        ("doc/doc.tex", 7),
    ]


@pytest.mark.unit
def test__inline_conditional__only_taken_branch_left() -> None:
    lines = _lines(f"{_FLAG_OFF}\n{{\\ifext(full)\\else(draft)\\fi}}")
    assert _texts(lines)[-1] == "{(draft)}"


@pytest.mark.unit
@pytest.mark.parametrize(
    "setup",
    [
        pytest.param("\\newif\\ifext", id="declared-never-set"),
        pytest.param("", id="undeclared"),
        pytest.param("\\newif\\ifext\n\\ifx\\a\\b\\exttrue\\fi", id="set-under-unknown-condition"),
        pytest.param(f"{_FLAG_OFF}\n\\let\\ifext\\iftrue", id="redefined-by-let"),
    ],
)
def test__unknown_value__both_branches_kept(setup: str) -> None:
    lines = _lines(f"{setup}\n{_BRANCHES}")
    assert _texts(lines) == [sl.text for sl in lines]


@pytest.mark.unit
def test__unless__inverts_known_flag() -> None:
    lines = _lines(f"{_FLAG_OFF}\n\\unless\\ifext NOT-EXT\\fi")
    assert _texts(lines)[-1] == " NOT-EXT"


@pytest.mark.unit
def test__iffalse_block__dropped_without_flags() -> None:
    assert _texts(_lines("a\n\\iffalse\nhidden\n\\fi\nb")) == ["a", "b"]


@pytest.mark.unit
def test__nested_unknown_conditional__fi_nesting_respected() -> None:
    text = f"{_FLAG_OFF}\n\\ifext\n\\ifx\\a\\b X\\else Y\\fi\nON\n\\else\n\\ifx\\a\\b Z\\fi\nOFF\n\\fi\nafter"
    assert _texts(_lines(text))[2:] == ["\\ifx\\a\\b Z\\fi", "OFF", "after"]


@pytest.mark.unit
def test__argument_tests_do_not_need_fi() -> None:
    text = f"{_FLAG_OFF}\n\\ifext\n\\ifdefempty{{\\x}}{{}}{{, \\x}}\nON\n\\fi\nafter"
    assert _texts(_lines(text))[2:] == ["after"]


@pytest.mark.unit
def test__setting_inside_dropped_branch__is_ignored() -> None:
    text = f"{_FLAG_OFF}\n\\iffalse\\exttrue\\fi\n{_BRANCHES}"
    assert "ON" not in _texts(_lines(text))


@pytest.mark.unit
def test__commented_conditionals__are_not_parsed() -> None:
    text = f"{_FLAG_OFF}\n% the \\ifext blocks below\n{_BRANCHES}\n% \\fi"
    assert _texts(_lines(text)) == [
        "\\newif\\ifext",
        "\\extfalse",
        "% the \\ifext blocks below",
        "before",
        "OFF",
        "after",
        "% \\fi",
    ]


@pytest.mark.unit
def test__verbatim_body__is_not_parsed() -> None:
    text = f"{_FLAG_OFF}\n\\begin{{verbatim}}\n\\ifext \\fi \\fi\n\\end{{verbatim}}\n{_BRANCHES}"
    assert _texts(_lines(text))[-3:] == ["before", "OFF", "after"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "tail",
    [pytest.param("\\fi", id="extra-fi"), pytest.param("\\ifext open", id="unclosed")],
)
def test__unbalanced_structure__lines_returned_untouched(tail: str) -> None:
    lines = _lines(f"{_FLAG_OFF}\n{_BRANCHES}\n{tail}")
    assert _texts(lines) == [sl.text for sl in lines]
