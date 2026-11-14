"""Песочница Jinja: атаки шаблона пака и пределы рендера (template-studio.md, раздел 9, срез T3)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from hse_doc_studio.infra.forms.form_renderer import FormOutputRenderer
from hse_doc_studio.infra.project_init.template_renderer import _render_text
from hse_doc_studio.infra.template.jinja_sandbox import (
    LATEX_SYNTAX,
    PACK_FILTERS,
    IsolatedRenderError,
    IsolationLimits,
    RenderLimits,
    SandboxedTemplateEnvironment,
    TemplateLimitError,
    form_environment,
    make_environment,
    pack_environment,
    render_isolated,
)
from jinja2.exceptions import SecurityError

_CONTEXT = {"project": {"name": "Проект", "authors": [{"name": "Иванов"}], "meta": {}}, "answers": {}}


def _env(**limits: float) -> SandboxedTemplateEnvironment:
    return make_environment(LATEX_SYNTAX, filters=PACK_FILTERS, limits=RenderLimits(**limits))  # type: ignore[arg-type]


def _render(source: str, env: SandboxedTemplateEnvironment | None = None) -> str:
    return (env or pack_environment()).render_source(source, _CONTEXT)


# ── Выход из песочницы ──────────────────────────────────────────


@pytest.mark.parametrize(
    "source",
    [
        "{{ ''.__class__ }}",
        "{{ ''.__class__.__mro__[1].__subclasses__() }}",
        "{{ ''['__class__'] }}",
        "{{ project.__class__ }}",
        "{{ project.meta.missing.__class__ }}",
        "{{ cycler.__init__.__globals__ }}",
        "{{ cycler.__init__.__globals__.os.popen('id').read() }}",
        "{{ joiner.__init__.__globals__ }}",
        "{{ namespace.__init__.__globals__ }}",
        "{{ lipsum.__globals__ }}",
        "{{ range.__self__ }}",
        "{{ '{0.__class__}'.format('') }}",
        "{{ project.authors.__getitem__ }}",
        "((* set x = ''.__class__ *)){{ x }}",
    ],
)
def test_private_attributes_are_refused(source: str) -> None:
    with pytest.raises(SecurityError):
        _render(source)


@pytest.mark.parametrize(
    "source",
    [
        # Атрибуты вне белого списка: байты, числа, функции, макросы.
        "{{ 'x'.encode('utf-8').decode('utf-8') }}",
        "{{ (1).real }}",
        "{{ cycler.next.__name__ }}",
        "((* macro m() *))((* endmacro *)){{ m.arguments }}",
        "{{ range(3).start }}",
    ],
)
def test_attributes_outside_whitelist_are_refused(source: str) -> None:
    with pytest.raises(SecurityError):
        _render(source)


@pytest.mark.parametrize(
    "source",
    [
        "((* do project.authors.append(1) *))",
        "((* do project.meta.update({'a': 1}) *))",
        "((* do project.meta.clear() *))",
    ],
)
def test_context_is_immutable(source: str) -> None:
    env = make_environment(LATEX_SYNTAX)
    env.add_extension("jinja2.ext.do")
    with pytest.raises(SecurityError):
        _render(source, env)


def test_allowed_template_features_work() -> None:
    source = (
        "((* set ns = namespace(words=[]) *))"
        "((* for w in 'b a'.split() *))((* set ns.words = ns.words + [w | upper] *))((* endfor *))"
        "{{ ns.words | join(',') }};{{ project.meta.get('x', 'def') }};"
        "((* for a in project.authors *)){{ loop.index }}{{ a.name | texesc }}((* if loop.last *)).((* endif *))"
        "((* endfor *));{{ project.meta.missing.chain }};{{ 'x' ~ 1 }};{{ range(3) | list }}"
    )
    assert _render(source) == "B,A;def;1Иванов.;;x1;[0, 1, 2]"


# ── Пределы ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "source",
    [
        "{{ range(10**9) | list }}",
        "((* for i in range(100001) *))((* endfor *))",
        "{{ range(0, 10**12, 2) | length }}",
    ],
)
def test_huge_range_is_refused(source: str) -> None:
    with pytest.raises(TemplateLimitError):
        _render(source)


def test_infinite_macro_recursion_is_stopped() -> None:
    with pytest.raises(TemplateLimitError, match="глубина"):
        _render("((* macro f(n) *)){{ f(n + 1) }}((* endmacro *)){{ f(0) }}")


def test_recursive_loop_depth_is_limited() -> None:
    source = "((* for x in [1] recursive *)){{ loop([1]) }}((* endfor *))"
    with pytest.raises(TemplateLimitError, match="глубина"):
        _render(source)


@pytest.mark.parametrize(
    "source",
    [
        # Пустые вложенные циклы: ни вызовов, ни вывода, время ловит обёртка `for`.
        "((* for i in range(100000) *))((* for j in range(100000) *))((* endfor *))((* endfor *))",
        # Экспоненциальная рекурсия неглубокая, но долгая.
        "((* macro f(n) *))((* if n *)){{ f(n - 1) }}{{ f(n - 1) }}((* endif *))((* endmacro *)){{ f(40) }}",
    ],
)
def test_render_time_is_limited(source: str) -> None:
    with pytest.raises(TemplateLimitError, match="дольше"):
        _render(source, _env(max_seconds=0.3))


@pytest.mark.parametrize(
    "source",
    [
        "((* for i in range(100000) *)){{ 'x' * 100 }}((* endfor *))",
        "{{ 'x' * 10**9 }}",
        "{{ [0] * 10**9 }}",
        "{{ 'x'.center(10**9) }}",
        "{{ 'x' | center(10**9) }}",
        "{{ 'x' | indent(10**9) }}",
        "((* set ns = namespace(s='x') *))((* for i in range(40) *))((* set ns.s = ns.s ~ ns.s *))((* endfor *))",
        "((* set ns = namespace(s='x') *))((* for i in range(40) *))((* set ns.s = ns.s + ns.s *))((* endfor *))",
        "{{ 2 ** 10000000 }}",
        "((* set ns = namespace(n=3) *))((* for i in range(30) *))((* set ns.n = ns.n * ns.n *))((* endfor *))",
    ],
)
def test_huge_output_is_refused(source: str) -> None:
    with pytest.raises(TemplateLimitError):
        _render(source)


def test_template_size_is_limited() -> None:
    env = _env(max_template_chars=1000)
    assert env.render_source("x" * 1000, {}) == "x" * 1000
    with pytest.raises(TemplateLimitError, match="шаблон больше"):
        env.render_source("x" * 1001, {})


def test_limits_reset_between_renders() -> None:
    env = _env(max_seconds=0.5)
    for _ in range(3):
        assert env.render_source("((* for i in range(1000) *)){{ i }}((* endfor *))", {}).endswith("999")


# ── Места рендера Студии ────────────────────────────────────────

_ATTACK = "{{ cycler.__init__.__globals__.os.popen('echo pwned').read() }}"


def test_pack_renderer_copies_attack_verbatim() -> None:
    assert _render_text(_ATTACK, {}, Path("evil.tex")) == _ATTACK


def test_form_renderer_returns_attack_verbatim() -> None:
    assert FormOutputRenderer().render(_ATTACK, {}) == _ATTACK


def test_form_environment_keeps_default_syntax() -> None:
    assert form_environment().render_source("{% if answers.x %}a{% else %}b{% endif %}\n", _CONTEXT) == "b\n"
    with pytest.raises(SecurityError):
        form_environment().render_source(_ATTACK, {})


# ── Отдельный процесс ───────────────────────────────────────────


def test_isolated_render_returns_text() -> None:
    assert render_isolated("{{ project.name | texesc }}&", {"project": {"name": "A_B"}}) == r"A\_B&"


def test_isolated_render_reports_sandbox_errors() -> None:
    with pytest.raises(IsolatedRenderError, match="SecurityError"):
        render_isolated(_ATTACK, {})


def test_isolated_render_is_killed_on_timeout() -> None:
    # Предел времени самой песочницы отключён: останавливает только таймер процесса.
    limits = IsolationLimits(timeout_seconds=2, render=RenderLimits(max_seconds=3600))
    source = "((* for i in range(100000) *))((* for j in range(100000) *))((* endfor *))((* endfor *))"
    with pytest.raises(IsolatedRenderError, match="процесс остановлен"):
        render_isolated(source, {}, limits=limits)


@pytest.mark.skipif(sys.platform != "linux", reason="RLIMIT_AS работает только на Linux")
def test_isolated_render_memory_is_limited() -> None:
    # printf-ширина обходит проверки аргументов: строку в 1 ГБ останавливает только предел памяти процесса.
    limits = IsolationLimits(memory_bytes=512 * 1024 * 1024)
    with pytest.raises(IsolatedRenderError, match="памяти"):
        render_isolated("{{ '%01000000000d' | format(1) }}", {}, limits=limits)


def test_isolated_render_rejects_unknown_profile() -> None:
    with pytest.raises(ValueError, match="профиль"):
        render_isolated("x", {}, profile="raw")
