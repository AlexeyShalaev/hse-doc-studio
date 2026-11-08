"""Статическое разрешение TeX-условий `\\ifX … \\else … \\fi` по флагам документа.

Шаблоны переключают части документа флагами `\\newif`: значение задаёт
отрендеренный `common/meta.tex` (`\\hseExtendedProposaltrue` / `…false`), а
текст держит обе ветки. Проверка, которая ищет по исходнику (например,
незаполненные `\\hseFill`), иначе видит и ветку, которая в PDF не попадёт.

Разрешаются только условия, значение которых известно из самого документа:
флаг объявлен `\\newif` и явно выставлен `\\Xtrue`/`\\Xfalse` в его графе
включений (плюс `\\iftrue`/`\\iffalse`). Всё остальное (`\\ifx`, `\\ifnum`,
флаги из `.sty`, флаг без явного значения) непрозрачно: обе ветки остаются,
как и раньше, — учитывается лишь вложенность их `\\fi`. Если структура
не сходится (лишний `\\fi`, незакрытое условие), разметка не трогается.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field, replace

from hse_doc_studio.infra.checks.utils import SourceLine

_TOKEN_RE = re.compile(r"\\([A-Za-z@]+)|\\.")

# Примитивы TeX/e-TeX/pdfTeX, закрываемые `\fi`, — их значение статически
# не вычислить, но вложенность учитывать нужно.
_PRIMITIVE_IFS: frozenset[str] = frozenset(
    {
        "if",
        "ifcat",
        "ifnum",
        "ifdim",
        "ifodd",
        "ifvmode",
        "ifhmode",
        "ifmmode",
        "ifinner",
        "ifvoid",
        "ifhbox",
        "ifvbox",
        "ifx",
        "ifeof",
        "ifcase",
        "ifdefined",
        "ifcsname",
        "iffontchar",
        "ifincsname",
        "ifpdfprimitive",
        "ifpdfabsnum",
        "ifpdfabsdim",
        "ifabsnum",
        "ifabsdim",
    }
)
_CONSTANT_IFS: dict[str, bool] = {"iftrue": True, "iffalse": False}

# Макросы-проверки с аргументами (etoolbox, ifthen): `\fi` им не нужен.
_ARGUMENT_TESTS: frozenset[str] = frozenset(
    {
        "ifthenelse",
        "ifdef",
        "ifndef",
        "ifundef",
        "ifdefempty",
        "ifdefvoid",
        "ifdefequal",
        "ifdefstring",
        "ifdefstrequal",
        "ifdefmacro",
        "ifdefparam",
        "ifdefprefix",
        "ifdefprotected",
        "ifdefcounter",
        "ifdeflength",
        "ifdefdimen",
        "ifcsdef",
        "ifcsundef",
        "ifcsempty",
        "ifcsvoid",
        "ifcsequal",
        "ifcsstring",
        "ifcsstrequal",
        "ifcsmacro",
        "ifcscounter",
        "ifcslength",
        "ifcsdimen",
        "ifltxcounter",
        "ifstrequal",
        "ifstrempty",
        "ifblank",
        "ifbool",
        "iftoggle",
        "ifboolexpr",
        "ifboolexpe",
        "ifnumcomp",
        "ifnumequal",
        "ifnumgreater",
        "ifnumless",
        "ifnumodd",
        "ifdimcomp",
        "ifdimequal",
        "ifdimgreater",
        "ifdimless",
        "ifinlist",
        "ifinlistcs",
        "ifrmnum",
    }
)

# После них `\ifX` — имя переопределяемого условия, а не проверка.
_DEFINERS: frozenset[str] = frozenset({"let", "def", "gdef", "edef", "xdef", "futurelet"})

_VERBATIM_BEGIN_RE = re.compile(r"\\begin\s*\{(verbatim\*?|Verbatim\*?|lstlisting|minted)\}")


class _UnbalancedError(Exception):
    """`\\else`/`\\fi` без открытого условия — разметку не трогаем."""


@dataclass
class _Frame:
    value: bool | None  # None — значение неизвестно, обе ветки остаются
    in_else: bool = False

    @property
    def emits(self) -> bool:
        return self.value is None or self.value != self.in_else


def _split_comment(line: str) -> tuple[str, str]:
    """Делит строку на код и `%`-комментарий (экранированный `\\%` — не комментарий)."""
    i = 0
    while i < len(line):
        if line[i] == "\\":
            i += 2
            continue
        if line[i] == "%":
            return line[:i], line[i:]
        i += 1
    return line, ""


@dataclass
class _State:
    """Флаги и стек условий в порядке чтения документа."""

    values: dict[str, bool | None] = field(default_factory=dict)  # объявленные `\\newif`
    stack: list[_Frame] = field(default_factory=list)
    resolved_any: bool = False

    def active(self) -> bool:
        return all(frame.emits for frame in self.stack)

    def certain(self) -> bool:
        return all(frame.value is not None for frame in self.stack)


class _LineScan:
    """Один проход по коду строки: собирает то, что попадает в документ."""

    def __init__(self, code: str, state: _State) -> None:
        self.code = code
        self.state = state
        self.out: list[str] = []
        self.pos = 0
        self._prev_name: str | None = None
        self._prev_end = 0

    def run(self) -> str:
        for m in _TOKEN_RE.finditer(self.code):
            self._token(m)
        self._flush(len(self.code))
        return "".join(self.out)

    def _flush(self, upto: int) -> None:
        if self.state.active():
            self.out.append(self.code[self.pos : upto])
        self.pos = upto

    def _token(self, m: re.Match[str]) -> None:
        name = m.group(1)
        adjacent = self._prev_name is not None and not self.code[self._prev_end : m.start()].strip()
        prev = self._prev_name if adjacent else None
        self._prev_name, self._prev_end = name, m.end()
        if name is None:
            return
        if name.startswith("if"):
            self._open(m, name, prev)
        elif name in ("else", "fi"):
            self._close(m, name)
        else:
            self._maybe_set(name)

    def _redefined(self, flag: str, prev: str | None) -> bool:
        """`\\newif\\ifX` объявляет флаг, `\\let\\ifX…` делает его значение неизвестным."""
        if prev == "newif":
            self.state.values.setdefault(flag, None)
            return True
        if prev in _DEFINERS:
            if flag in self.state.values:
                self.state.values[flag] = None
            return True
        return False

    def _open(self, m: re.Match[str], name: str, prev: str | None) -> None:
        flag = name[2:]
        if self._redefined(flag, prev) or name in _ARGUMENT_TESTS:
            return
        if flag in self.state.values or name in _CONSTANT_IFS:
            self._open_known(m, name, prev)
        elif name in _PRIMITIVE_IFS or not self.code[m.end() :].lstrip().startswith("{"):
            self.state.stack.append(_Frame(None))

    def _open_known(self, m: re.Match[str], name: str, prev: str | None) -> None:
        value = _CONSTANT_IFS.get(name, self.state.values.get(name[2:]))
        if value is None:
            self.state.stack.append(_Frame(None))
            return
        start = m.start()
        if prev == "unless":
            value = not value
            start = self.code.rfind("\\unless", 0, start)
        self._flush(start)
        self.state.stack.append(_Frame(value))
        self.state.resolved_any = True
        self.pos = m.end()

    def _close(self, m: re.Match[str], name: str) -> None:
        if not self.state.stack:
            raise _UnbalancedError
        top = self.state.stack[-1]
        known = top.value is not None
        if known:
            self._flush(m.start())
        if name == "else":
            top.in_else = True
        else:
            self.state.stack.pop()
        if known:
            self.pos = m.end()

    def _maybe_set(self, name: str) -> None:
        for suffix, value in (("true", True), ("false", False)):
            flag = name.removesuffix(suffix)
            if flag != name and flag in self.state.values:
                if self.state.active():
                    self.state.values[flag] = value if self.state.certain() else None
                return


class _DocumentScan:
    def __init__(self) -> None:
        self.state = _State()
        self._verbatim_end: str | None = None

    def _split(self, line: str) -> tuple[str, str]:
        """Код для разбора и хвост строки, который не разбирается (комментарий, verbatim)."""
        code, comment = _split_comment(line)
        verbatim = _VERBATIM_BEGIN_RE.search(code)
        if verbatim is None:
            return code, comment
        # Тело verbatim не разбираем: `\\if` там — просто текст.
        end_marker = f"\\end{{{verbatim.group(1)}}}"
        if end_marker not in line[verbatim.end() :]:
            self._verbatim_end = end_marker
        return code[: verbatim.end()], line[verbatim.end() :]

    def feed(self, sl: SourceLine) -> SourceLine | None:
        """Строка, как она попадает в документ, или None, если от неё ничего нет."""
        if self._verbatim_end is not None:
            if self._verbatim_end in sl.text:
                self._verbatim_end = None
            return sl if self.state.active() else None
        was_active = self.state.active()
        code, tail = self._split(sl.text)
        text = _LineScan(code, self.state).run()
        if self.state.active():
            text += tail
        if text == sl.text and was_active:
            return sl
        if text.strip():
            return replace(sl, text=text)
        # В строке только выключенная ветка или сами `\\ifX`/`\\fi`.
        return None


def resolve_conditionals(lines: Sequence[SourceLine]) -> list[SourceLine]:
    """Убирает из развёрнутого документа ветки условий, не попадающие в вывод.

    Строки целиком из выключенной ветки выпадают, у частично затронутых
    вырезаются выключенный кусок и сами `\\ifX`/`\\else`/`\\fi` разрешённых
    условий; файл и номер строки остаются прежними. Без разрешимых условий
    (или при несходящейся структуре) возвращает строки как есть.
    """
    scan = _DocumentScan()
    try:
        fed = [scan.feed(sl) for sl in lines]
    except _UnbalancedError:
        return list(lines)
    if scan.state.stack or not scan.state.resolved_any:
        return list(lines)
    return [sl for sl in fed if sl is not None]
