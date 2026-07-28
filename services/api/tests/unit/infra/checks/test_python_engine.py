from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.core.enums import CheckEngine, CheckSeverity
from hse_doc_studio.infra.checks.python_engine import PythonCheckEngine

from tests.factories import make_check_rule

engine = PythonCheckEngine()


def _tex(folder: Path, filename: str, content: str) -> None:
    (folder / filename).write_text(content, encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────
# Happy path: snippet runs, registers violations
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test__python_engine__inline_code_reports_violation(tmp_path: Path) -> None:
    _tex(tmp_path, "main.tex", r"\section{X}")
    rule = make_check_rule(
        rule_id="p1",
        engine=CheckEngine.python,
        params={
            "code": "ctx.violation('hello', file='main.tex', line=1)",
        },
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1
    assert results[0].message == "hello"
    assert results[0].location.file == "main.tex"
    assert results[0].location.line == 1


@pytest.mark.unit
def test__python_engine__no_violations__no_results(tmp_path: Path) -> None:
    rule = make_check_rule(
        rule_id="p2",
        engine=CheckEngine.python,
        params={"code": "ctx.ok()"},
    )
    assert engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None) == []


@pytest.mark.unit
def test__python_engine__multiple_violations__all_returned(tmp_path: Path) -> None:
    rule = make_check_rule(
        rule_id="p3",
        engine=CheckEngine.python,
        params={
            "code": ("ctx.violation('a', line=1)\nctx.violation('b', line=2)\nctx.violation('c', line=3)\n"),
        },
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert [r.message for r in results] == ["a", "b", "c"]


# ──────────────────────────────────────────────────────────────────────────
# CheckContext API
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test__python_engine__ctx_read__returns_file_contents(tmp_path: Path) -> None:
    _tex(tmp_path, "main.tex", "hello world")
    rule = make_check_rule(
        rule_id="p4",
        engine=CheckEngine.python,
        params={
            "code": ("text = ctx.read('main.tex')\nif 'hello' in text:\n    ctx.violation('found hello')\n"),
        },
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1
    assert results[0].message == "found hello"


@pytest.mark.unit
def test__python_engine__ctx_files__returns_matching_paths(tmp_path: Path) -> None:
    _tex(tmp_path, "a.tex", "")
    _tex(tmp_path, "b.tex", "")
    _tex(tmp_path, "c.txt", "")
    rule = make_check_rule(
        rule_id="p5",
        engine=CheckEngine.python,
        params={
            "code": ("files = ctx.files('*.tex')\nctx.violation(f'count={len(files)}')\n"),
        },
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1
    assert results[0].message == "count=2"


@pytest.mark.unit
def test__python_engine__ctx_count__counts_pattern_across_files(tmp_path: Path) -> None:
    _tex(tmp_path, "a.tex", r"\section{1} \section{2}")
    _tex(tmp_path, "b.tex", r"\section{3}")
    rule = make_check_rule(
        rule_id="p6",
        engine=CheckEngine.python,
        params={
            "code": ("n = ctx.count(r'\\\\section\\{', '*.tex')\nctx.violation(f'sections={n}')\n"),
        },
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1
    assert results[0].message == "sections=3"


@pytest.mark.unit
def test__python_engine__ctx_find__returns_file_line_tuples(tmp_path: Path) -> None:
    _tex(tmp_path, "main.tex", "first\n\\todo{x}\nthird\n\\todo{y}")
    rule = make_check_rule(
        rule_id="p7",
        engine=CheckEngine.python,
        params={
            "code": (
                "for f, ln, text in ctx.find(r'\\\\todo', '*.tex'):\n"
                "    ctx.violation(f'TODO at {f}:{ln}', file=f, line=ln)\n"
            ),
        },
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 2
    assert results[0].location.line == 2
    assert results[1].location.line == 4


@pytest.mark.unit
def test__python_engine__ctx_files__skips_build_and_studio_dirs(tmp_path: Path) -> None:
    _tex(tmp_path, "main.tex", "")
    for service in (".build", ".hse-studio"):
        (tmp_path / service).mkdir()
        _tex(tmp_path / service, "leftover.tex", "")
    rule = make_check_rule(
        rule_id="skip-service-dirs",
        engine=CheckEngine.python,
        params={"code": "ctx.violation(','.join(ctx.files('**/*.tex')))"},
    )

    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)

    assert results[0].message == "main.tex"


@pytest.mark.unit
def test__python_engine__ctx_files__star_does_not_cross_directories(tmp_path: Path) -> None:
    (tmp_path / "thesis" / "nested").mkdir(parents=True)
    _tex(tmp_path / "thesis", "thesis.tex", "")
    _tex(tmp_path / "thesis" / "nested", "deep.tex", "")
    rule = make_check_rule(
        rule_id="glob-depth",
        engine=CheckEngine.python,
        params={"code": "ctx.violation(str(len(ctx.files('thesis/*.tex'))))"},
    )

    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "thesis/thesis.tex", None)

    assert results[0].message == "1"


@pytest.mark.unit
def test__python_engine__ctx_files__base_dir_given__teammate_files_excluded(tmp_path: Path) -> None:
    for author in ("ivanov", "petrov"):
        (tmp_path / author).mkdir()
        _tex(tmp_path / author, "thesis.tex", "")
    rule = make_check_rule(
        rule_id="base-scoped",
        engine=CheckEngine.python,
        params={"code": "ctx.violation(','.join(ctx.files('**/*.tex')))"},
    )

    results = engine.run(
        rule,
        CheckSeverity.warn,
        tmp_path,
        "doc1",
        "ivanov/thesis.tex",
        None,
        base_dir="ivanov",
    )

    assert results[0].message == str(Path("ivanov/thesis.tex"))


@pytest.mark.unit
def test__python_engine__ctx_doc_find__scans_include_chain_only(tmp_path: Path) -> None:
    (tmp_path / "thesis").mkdir()
    (tmp_path / "common").mkdir()
    (tmp_path / "operator_manual").mkdir()
    _tex(tmp_path / "thesis", "thesis.tex", "\\input{../common/preamble}\nbody\n")
    _tex(tmp_path / "common", "preamble.tex", "% TODO дописать преамбулу\n")
    _tex(tmp_path / "operator_manual", "operator_manual.tex", "% TODO чужой документ\n")
    rule = make_check_rule(
        rule_id="doc-find",
        engine=CheckEngine.python,
        params={
            "code": (
                "for f, ln, _ in ctx.doc_find(r'^\\s*%\\s*TODO\\b'):\n    ctx.violation(f'{f}:{ln}', file=f, line=ln)\n"
            ),
        },
    )

    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "thesis/thesis.tex", None)

    assert [r.message for r in results] == ["common/preamble.tex:1"]


@pytest.mark.unit
def test__python_engine__ctx_doc_count__ignores_other_documents(tmp_path: Path) -> None:
    (tmp_path / "thesis").mkdir()
    (tmp_path / "operator_manual").mkdir()
    _tex(tmp_path / "thesis", "thesis.tex", "\\begin{figure}\n\\caption{ok}\n\\end{figure}\n")
    _tex(tmp_path / "operator_manual", "operator_manual.tex", "\\begin{figure}\n\\end{figure}\n")
    rule = make_check_rule(
        rule_id="doc-count",
        engine=CheckEngine.python,
        params={
            "code": (
                "figures = ctx.doc_count(r'\\\\begin\\s*\\{\\s*figure\\b')\n"
                "captions = ctx.doc_count(r'\\\\caption\\s*\\{')\n"
                "ctx.violation(f'{figures}/{captions}')\n"
            ),
        },
    )

    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "thesis/thesis.tex", None)

    assert results[0].message == "1/1"


@pytest.mark.unit
def test__python_engine__params_accessible_from_snippet(tmp_path: Path) -> None:
    rule = make_check_rule(
        rule_id="p8",
        engine=CheckEngine.python,
        params={
            "code": "ctx.violation(ctx.params.get('threshold', 'default'))",
            "threshold": "42",
        },
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1
    assert results[0].message == "42"


# ──────────────────────────────────────────────────────────────────────────
# Sandboxing — restricted builtins
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    ("rule_id", "code"),
    [
        ("sandbox-open", "open('secret.txt').read()"),
        ("sandbox-import", "import os\nctx.violation('should not get here')"),
    ],
)
def test__python_engine__blocked_builtin_used__returns_diag(tmp_path: Path, rule_id: str, code: str) -> None:
    _tex(tmp_path, "secret.txt", "leak me")
    rule = make_check_rule(rule_id=rule_id, engine=CheckEngine.python, params={"code": code})

    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)

    assert len(results) == 1
    assert "Ошибка выполнения" in results[0].message


@pytest.mark.unit
def test__python_engine__re_module_is_available(tmp_path: Path) -> None:
    _tex(tmp_path, "main.tex", "alpha beta gamma")
    rule = make_check_rule(
        rule_id="re-ok",
        engine=CheckEngine.python,
        params={
            "code": ("m = re.search('(.+) beta', ctx.read('main.tex'))\nif m:\n    ctx.violation(m.group(1))\n"),
        },
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1
    assert results[0].message == "alpha"


# ──────────────────────────────────────────────────────────────────────────
# Error handling
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(("rule_id", "code"), [("syntax", "this is not python"), ("runtime", "1/0")])
def test__python_engine__code_raises__returns_diag(tmp_path: Path, rule_id: str, code: str) -> None:
    rule = make_check_rule(rule_id=rule_id, engine=CheckEngine.python, params={"code": code})

    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)

    assert len(results) == 1
    assert "Ошибка выполнения" in results[0].message


@pytest.mark.unit
@pytest.mark.parametrize(
    ("rule_id", "params"),
    [("empty", {}), ("missing-script", {"script": "nonexistent.py"})],
)
def test__python_engine__no_code_to_run__no_results(tmp_path: Path, rule_id: str, params: dict[str, str]) -> None:
    rule = make_check_rule(rule_id=rule_id, engine=CheckEngine.python, params=params)

    assert engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None) == []


@pytest.mark.unit
def test__python_engine__script_file_loaded(tmp_path: Path) -> None:
    (tmp_path / ".hse-studio").mkdir()
    (tmp_path / ".hse-studio" / "check.py").write_text(
        "ctx.violation('from script')",
        encoding="utf-8",
    )
    rule = make_check_rule(
        rule_id="script",
        engine=CheckEngine.python,
        params={"script": ".hse-studio/check.py"},
    )

    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)

    assert len(results) == 1
    assert results[0].message == "from script"


@pytest.mark.unit
def test__python_engine__timeout__returns_diag(tmp_path: Path) -> None:
    # The sandbox's globals expose no `__import__` (see _build_globals), so the
    # slow code can't `import time` to block cheaply. A real timeout leaves this
    # rule's thread running as an orphaned daemon for the rest of the process —
    # there's no way to force-kill it — so a *bounded* loop is used instead of a
    # `while True` one, to cap how long the leftover thread pegs a core and
    # starves the GIL for tests that run afterwards in this session.
    rule = make_check_rule(
        rule_id="slow",
        engine=CheckEngine.python,
        params={
            "code": "x = 0\nfor _ in range(60_000_000):\n    x += 1\n",
            "timeout": 0.2,
        },
    )
    results = engine.run(rule, CheckSeverity.warn, tmp_path, "doc1", "main.tex", None)
    assert len(results) == 1
    assert "таймаут" in results[0].message.lower()
