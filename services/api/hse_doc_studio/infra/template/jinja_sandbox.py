"""Песочница Jinja для шаблонов паков (template-studio.md, раздел 9 и срез T3).

Пак пишет посторонний автор, а Jinja в обычном `Environment` даёт шаблону весь Python:
`{{ cycler.__init__.__globals__.os.popen('id').read() }}` исполняется в процессе api.
Здесь единственная фабрика окружений Студии: все места, где рендерится Jinja, берут окружение отсюда.

Слои защиты:
  * `ImmutableSandboxedEnvironment`: служебные атрибуты (`_…`, атрибуты функций и кадров) закрыты,
    методы, меняющие списки и словари контекста, запрещены;
  * белый список атрибутов по типам (`_SAFE_ATTRS`): шаблон видит методы строк, `get/items/keys/values`
    словарей, переменные цикла и `namespace`, остальное это `SecurityError`, а не пустая строка;
  * пределы (`RenderLimits`): размер шаблона, размер вывода и промежуточных строк и списков, время
    рендера, глубина вызовов макросов и `range`. Время проверяется на каждом вызове, обращении к атрибуту,
    фильтре, операторе и шаге каждого цикла `for` (итерируемое оборачивается при разборе шаблона);
  * `render_isolated`: рендер в отдельном процессе с пределом времени и памяти для черновых паков.
    В процессе api память ограничить нельзя, поэтому чужой непроверенный пак рендерится только так.

Вывод для честных шаблонов байт в байт совпадает с обычным `Environment` с теми же настройками:
это проверяет тест на всех версиях всех паков репозитория.
"""

from __future__ import annotations

import contextlib
import html
import multiprocessing
import platform
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import cache, wraps
from typing import TYPE_CHECKING, Any, NoReturn

from jinja2 import BaseLoader, ChainableUndefined, Undefined, nodes, pass_eval_context
from jinja2.exceptions import SecurityError
from jinja2.runtime import LoopContext, markup_join, str_join
from jinja2.sandbox import ImmutableSandboxedEnvironment
from jinja2.utils import Cycler, Namespace, _PassArg
from jinja2.visitor import NodeTransformer

if TYPE_CHECKING:
    from multiprocessing.connection import Connection

    from jinja2 import Template
    from jinja2.nodes import EvalContext
    from jinja2.runtime import Context


class TemplateLimitError(SecurityError):
    """Шаблон упёрся в предел песочницы (размер, время, глубина, `range`)."""


@dataclass(frozen=True, slots=True)
class RenderLimits:
    # Самый большой файл паков репозитория 63 КБ, вывод того же порядка: пределы с запасом в десятки раз.
    max_template_chars: int = 2_000_000
    max_output_chars: int = 8_000_000
    max_seconds: float = 5.0
    max_call_depth: int = 50
    max_range: int = 100_000
    max_int_bits: int = 1_000_000


DEFAULT_LIMITS = RenderLimits()


@dataclass(frozen=True, slots=True)
class TemplateSyntax:
    """Разметка шаблона: разделители и пробелы. Остальное у всех окружений Студии общее."""

    block_start: str = "{%"
    block_end: str = "%}"
    variable_start: str = "{{"
    variable_end: str = "}}"
    comment_start: str = "{#"
    comment_end: str = "#}"
    trim_blocks: bool = False
    lstrip_blocks: bool = False
    keep_trailing_newline: bool = True


# Jinja по умолчанию: анкеты и их шаблоны вывода (`answers.*`).
DEFAULT_SYNTAX = TemplateSyntax()
# Файлы пака: LaTeX сталкивается с `{% %}` и `{# #}` (`\caption{% …}`, `{#1}`), поэтому блоки и комментарии
# пишутся `((* *))` и `((# #))`, плейсхолдер остаётся `{{ }}` (подробности в template_renderer._render_text).
LATEX_SYNTAX = TemplateSyntax(block_start="((*", block_end="*))", comment_start="((#", comment_end="#))")
# CI-файлы git-синхронизации: YAML и shell полны `{{ }}`, `{% %}` и `${...}`.
CI_YAML_SYNTAX = TemplateSyntax(
    block_start="[%",
    block_end="%]",
    variable_start="[[",
    variable_end="]]",
    trim_blocks=True,
    lstrip_blocks=True,
)


# ── Фильтры паков ───────────────────────────────────────────────

# Порядок важен: обратная косая первой, иначе удвоятся замены, которые сами её вводят.
_TEX_ESCAPES: tuple[tuple[str, str], ...] = (
    ("\\", r"\textbackslash{}"),
    ("&", r"\&"),
    ("%", r"\%"),
    ("$", r"\$"),
    ("#", r"\#"),
    ("_", r"\_"),
    ("{", r"\{"),
    ("}", r"\}"),
    ("~", r"\textasciitilde{}"),
    ("^", r"\textasciicircum{}"),
)


def texesc(value: Any) -> str:
    """Фильтр `texesc`: экранирует спецсимволы LaTeX в данных пользователя (имена, темы с `&`, `_`, `%`)."""
    text = "" if value is None else str(value)
    for char, repl in _TEX_ESCAPES:
        text = text.replace(char, repl)
    return text


def xmlesc(value: Any) -> str:
    """Фильтр `xmlesc`: экранирует XML (и кавычки) для плейсхолдеров в XML слайдов pptx."""
    return html.escape("" if value is None else str(value), quote=True)


PACK_FILTERS: Mapping[str, Callable[..., Any]] = {"texesc": texesc, "xmlesc": xmlesc}


# ── Белый список атрибутов ──────────────────────────────────────

_ANY_ATTR: frozenset[str] = frozenset({"*"})
_STR_ATTRS = frozenset(name for name in dir(str) if not name.startswith("_"))
# Порядок важен: первый подходящий тип решает (bool это int, Markup это str).
_SAFE_ATTRS: tuple[tuple[type, frozenset[str]], ...] = (
    (Namespace, _ANY_ATTR),
    (str, _STR_ATTRS | {"striptags", "unescape"}),
    (dict, frozenset({"get", "items", "keys", "values"})),
    (list, frozenset({"count", "index"})),
    (tuple, frozenset({"count", "index"})),
    (
        LoopContext,
        frozenset(
            {
                "changed",
                "cycle",
                "depth",
                "depth0",
                "first",
                "index",
                "index0",
                "last",
                "length",
                "nextitem",
                "previtem",
                "revindex",
                "revindex0",
            }
        ),
    ),
    (Cycler, frozenset({"current", "items", "next", "reset"})),
)


def _attr_allowed(obj: Any, attr: str) -> bool:
    if isinstance(obj, Undefined):
        return True
    for typ, allowed in _SAFE_ATTRS:
        if isinstance(obj, typ):
            return allowed is _ANY_ATTR or attr in allowed
    return False


# ── Состояние одного рендера ────────────────────────────────────


@dataclass(slots=True)
class _RenderState:
    deadline: float
    depth: int = 0


_STATE: ContextVar[_RenderState | None] = ContextVar("hds_jinja_render_state", default=None)


def _sized(value: Any) -> int | None:
    if isinstance(value, str | bytes | list | tuple | dict):
        return len(value)
    return None


class _GuardTransformer(NodeTransformer):
    """Оборачивает итерируемое каждого `for` и каждый `~` в проверки песочницы.

    Пустой цикл не вызывает ни функций, ни атрибутов: без обёртки вложенные циклы шли бы мимо предела
    времени. `~` склеивает строки без вызова: без обёртки удвоение строки в цикле обходило бы предел размера.
    """

    def visit_For(self, node: nodes.For) -> nodes.Node:  # noqa: N802 — имя задаёт NodeTransformer
        self.generic_visit(node)
        node.iter = _env_call("sandbox_iter", node.iter, node.lineno)  # type: ignore[arg-type]
        return node

    def visit_Concat(self, node: nodes.Concat) -> nodes.Node:  # noqa: N802 — имя задаёт NodeTransformer
        self.generic_visit(node)
        return _env_call("sandbox_concat", nodes.List(node.nodes, lineno=node.lineno), node.lineno)


def _env_call(attr: str, arg: nodes.Expr, lineno: int) -> nodes.Call:
    return nodes.Call(nodes.EnvironmentAttribute(attr, lineno=lineno), [arg], [], None, None, lineno=lineno)


class SandboxedTemplateEnvironment(ImmutableSandboxedEnvironment):
    """Песочное окружение Студии: белый список атрибутов и пределы рендера (`RenderLimits`)."""

    intercepted_binops = frozenset({"*", "**", "+", "%"})

    def __init__(
        self,
        *,
        syntax: TemplateSyntax,
        undefined: type[Undefined] = ChainableUndefined,
        loader: BaseLoader | None = None,
        filters: Mapping[str, Callable[..., Any]] | None = None,
        limits: RenderLimits = DEFAULT_LIMITS,
    ) -> None:
        super().__init__(
            block_start_string=syntax.block_start,
            block_end_string=syntax.block_end,
            variable_start_string=syntax.variable_start,
            variable_end_string=syntax.variable_end,
            comment_start_string=syntax.comment_start,
            comment_end_string=syntax.comment_end,
            trim_blocks=syntax.trim_blocks,
            lstrip_blocks=syntax.lstrip_blocks,
            keep_trailing_newline=syntax.keep_trailing_newline,
            undefined=undefined,
            loader=loader,
            autoescape=False,
        )
        self.limits = limits
        self.filters.update(filters or {})
        # Фильтры вызываются напрямую, мимо `call`: проверки ставим обёрткой.
        self.filters = {name: self._guard_filter(func) for name, func in self.filters.items()}
        self.globals["range"] = self._safe_range

    # ── Рендер ──

    def render_source(self, source: str, context: Mapping[str, Any]) -> str:
        """Рендер шаблона из строки (файл пака, шаблон вывода анкеты) с пределами."""
        return self.render_with_limits(self.from_string(source), context)

    def render_template(self, name: str, context: Mapping[str, Any]) -> str:
        """Рендер шаблона загрузчика по имени с пределами."""
        return self.render_with_limits(self.get_template(name), context)

    def render_with_limits(self, template: Template, context: Mapping[str, Any]) -> str:
        """То же, что `Template.render`, плюс предел времени, глубины и размера вывода."""
        token = _STATE.set(_RenderState(deadline=time.monotonic() + self.limits.max_seconds))
        try:
            ctx = template.new_context(dict(context))
            try:
                return self.concat(self._collect(template.root_render_func(ctx)))
            except Exception:
                self.handle_exception()
        finally:
            _STATE.reset(token)

    def _collect(self, chunks: Iterable[str]) -> list[str]:
        parts: list[str] = []
        total = 0
        for chunk in chunks:
            total += len(chunk)
            if total > self.limits.max_output_chars:
                raise TemplateLimitError(f"вывод шаблона больше {self.limits.max_output_chars} знаков")
            self._tick()
            parts.append(chunk)
        return parts

    # ── Разбор: размер и обёртки циклов ──

    def _parse(self, source: str, name: str | None, filename: str | None) -> nodes.Template:
        if len(source) > self.limits.max_template_chars:
            raise TemplateLimitError(f"шаблон больше {self.limits.max_template_chars} знаков")
        template = super()._parse(source, name, filename)
        guarded = _GuardTransformer().visit(template)
        guarded.set_environment(self)
        return guarded

    def sandbox_iter(self, iterable: Any) -> Any:
        if isinstance(iterable, Undefined):
            return iterable
        return self._guarded_iter(iter(iterable))

    def _guarded_iter(self, iterator: Iterator[Any]) -> Iterator[Any]:
        for item in iterator:
            self._tick()
            yield item

    @pass_eval_context
    def sandbox_concat(self, eval_ctx: EvalContext, items: list[Any]) -> str:
        # Тот же выбор, что у кодогенератора Jinja для `~`: markup_join при автоэкранировании, иначе str_join.
        result = markup_join(items) if eval_ctx.autoescape else str_join(items)
        self._check_result(result)
        return result

    # ── Перехват доступа и вызовов ──

    def is_safe_attribute(self, obj: Any, attr: str, value: Any) -> bool:
        return super().is_safe_attribute(obj, attr, value) and _attr_allowed(obj, attr)

    def unsafe_undefined(self, obj: Any, attribute: str) -> NoReturn:
        # Обычная песочница отдаёт Undefined, а ChainableUndefined молча печатает пустую строку: отказываем явно.
        raise SecurityError(f"доступ к атрибуту {attribute!r} объекта {type(obj).__name__!r} запрещён")

    def getattr(self, obj: Any, attribute: str) -> Any:
        self._tick()
        return super().getattr(obj, attribute)

    def getitem(self, obj: Any, argument: Any) -> Any:
        self._tick()
        return super().getitem(obj, argument)

    def call(__self, __context: Context, __obj: Any, *args: Any, **kwargs: Any) -> Any:  # noqa: N805
        __self._tick()
        if not __self.is_safe_callable(__obj):
            raise SecurityError(f"{__obj!r} is not safely callable")
        __self._check_args(args, kwargs)
        state = _STATE.get()
        if state is None:
            result = __context.call(__obj, *args, **kwargs)
        else:
            if state.depth >= __self.limits.max_call_depth:
                raise TemplateLimitError(f"глубина вызовов больше {__self.limits.max_call_depth}")
            state.depth += 1
            try:
                result = __context.call(__obj, *args, **kwargs)
            finally:
                state.depth -= 1
        __self._check_result(result)
        return result

    def call_binop(self, context: Context, operator: str, left: Any, right: Any) -> Any:
        self._tick()
        if operator == "*":
            self._check_repeat(left, right)
            self._check_repeat(right, left)
        elif operator == "**":
            self._check_power(left, right)
        result = self.binop_table[operator](left, right)
        self._check_result(result)
        return result

    # ── Проверки ──

    def _tick(self) -> None:
        state = _STATE.get()
        if state is not None and time.monotonic() > state.deadline:
            raise TemplateLimitError(f"рендер дольше {self.limits.max_seconds} с")

    def _safe_range(self, *args: int) -> range:
        rng = range(*args)
        if len(rng) > self.limits.max_range:
            raise TemplateLimitError(f"range больше {self.limits.max_range} элементов")
        return rng

    def _check_args(self, args: Iterable[Any], kwargs: Mapping[str, Any]) -> None:
        # Ширина и число повторов: `'x'.center(10**9)`, `batch(10**9, 'x')` выделяют память до проверки результата.
        for value in (*args, *kwargs.values()):
            if isinstance(value, int) and not isinstance(value, bool) and abs(value) > self.limits.max_output_chars:
                raise TemplateLimitError(f"число {value} больше предела аргумента {self.limits.max_output_chars}")

    def _check_result(self, value: Any) -> None:
        size = _sized(value)
        if size is not None and size > self.limits.max_output_chars:
            raise TemplateLimitError(f"значение больше {self.limits.max_output_chars} элементов")
        if isinstance(value, int) and value.bit_length() > self.limits.max_int_bits:
            raise TemplateLimitError(f"число длиннее {self.limits.max_int_bits} бит")

    def _check_repeat(self, seq: Any, times: Any) -> None:
        size = _sized(seq)
        if size is not None and isinstance(times, int) and size * times > self.limits.max_output_chars:
            raise TemplateLimitError(f"повтор длиннее {self.limits.max_output_chars} элементов")

    def _check_power(self, base: Any, exp: Any) -> None:
        if (
            isinstance(base, int)
            and isinstance(exp, int)
            and abs(base) > 1
            and base.bit_length() * exp > self.limits.max_int_bits
        ):
            raise TemplateLimitError(f"степень длиннее {self.limits.max_int_bits} бит")

    def _guard_filter(self, func: Callable[..., Any]) -> Callable[..., Any]:
        # Первые аргументы фильтра это служебный (context, eval_ctx, environment), если он есть, и значение.
        skip = 1 if _PassArg.from_obj(func) is None else 2

        @wraps(func)  # переносит jinja_pass_arg: Jinja по нему решает, что передать первым аргументом
        def guarded(*args: Any, **kwargs: Any) -> Any:
            self._tick()
            self._check_args(args[skip:], kwargs)
            result = func(*args, **kwargs)
            self._check_result(result)
            return result

        return guarded


def make_environment(
    syntax: TemplateSyntax,
    *,
    undefined: type[Undefined] = ChainableUndefined,
    loader: BaseLoader | None = None,
    filters: Mapping[str, Callable[..., Any]] | None = None,
    limits: RenderLimits = DEFAULT_LIMITS,
) -> SandboxedTemplateEnvironment:
    """Фабрика окружений Jinja Студии. Обычный `Environment` в коде Студии не создаётся."""
    return SandboxedTemplateEnvironment(
        syntax=syntax, undefined=undefined, loader=loader, filters=filters, limits=limits
    )


@cache
def pack_environment() -> SandboxedTemplateEnvironment:
    """Файлы паков: LaTeX-разметка, ChainableUndefined, фильтры `texesc` и `xmlesc`."""
    return make_environment(LATEX_SYNTAX, filters=PACK_FILTERS)


@cache
def form_environment() -> SandboxedTemplateEnvironment:
    """Шаблоны вывода анкет: разметка Jinja по умолчанию, ChainableUndefined."""
    return make_environment(DEFAULT_SYNTAX)


_PROFILES: Mapping[str, Callable[[], SandboxedTemplateEnvironment]] = {
    "pack": pack_environment,
    "form": form_environment,
}


# ── Рендер в отдельном процессе ─────────────────────────────────


@dataclass(frozen=True, slots=True)
class IsolationLimits:
    """Пределы процесса для черновых паков (раздел 9: 10 с и ограниченная память)."""

    timeout_seconds: float = 10.0
    memory_bytes: int = 512 * 1024 * 1024
    render: RenderLimits = field(default_factory=RenderLimits)


class IsolatedRenderError(SecurityError):
    """Рендер в отдельном процессе не удался: шаблон упал, превысил предел или процесс убит."""


def render_isolated(
    source: str,
    context: Mapping[str, Any],
    *,
    profile: str = "pack",
    limits: IsolationLimits | None = None,
) -> str:
    """Рендер чужого шаблона в отдельном процессе с пределом времени и памяти.

    Процесс запускается заново (spawn): ни памяти, ни дескрипторов api он не наследует. Предел памяти ставится
    через RLIMIT_AS там, где он есть (Linux); предел времени общий, по нему процесс убивается.
    """
    if profile not in _PROFILES:
        raise ValueError(f"неизвестный профиль окружения: {profile}")
    limits = limits or IsolationLimits()
    ctx = multiprocessing.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(
        target=_isolated_worker,
        args=(child_conn, profile, source, dict(context), limits),
        daemon=True,
    )
    proc.start()
    child_conn.close()
    try:
        if not parent_conn.poll(limits.timeout_seconds):
            raise IsolatedRenderError(f"рендер дольше {limits.timeout_seconds} с, процесс остановлен")
        try:
            status, payload = parent_conn.recv()
        except EOFError as exc:
            raise IsolatedRenderError(f"процесс рендера завершился без ответа (код {proc.exitcode})") from exc
    finally:
        proc.kill()
        proc.join()
        parent_conn.close()
    if status != "ok":
        raise IsolatedRenderError(payload)
    return str(payload)


def _isolated_worker(
    conn: Connection, profile: str, source: str, context: dict[str, Any], limits: IsolationLimits
) -> None:
    _limit_memory(limits.memory_bytes)
    try:
        env = _PROFILES[profile]()
        env.limits = limits.render
        conn.send(("ok", env.render_source(source, context)))
    except MemoryError:
        conn.send(("error", "рендер превысил предел памяти"))
    except Exception as exc:  # noqa: BLE001 — ответ родителю обязан уйти при любой ошибке шаблона
        conn.send(("error", f"{type(exc).__name__}: {exc}"))
    finally:
        conn.close()


def _limit_memory(memory_bytes: int) -> None:
    if platform.system() != "Linux":
        return  # RLIMIT_AS есть только на Linux; на macOS и Windows остаётся предел времени
    import resource  # noqa: PLC0415 — модуля нет на Windows

    with contextlib.suppress(ValueError, OSError):
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
