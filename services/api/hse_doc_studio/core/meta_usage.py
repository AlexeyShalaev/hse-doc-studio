"""Где печатаются поля проекта: разбор динамических инклудов шаблона и поиск их макросов в исходниках документов.

Поля проекта доходят до PDF через динамические инклуды (`common/meta.tex.j2` и т.п., см. `DynamicInclude`):
инклуд объявляет макрос `\\hseX`, тело которого подставляет `project.meta.<ключ>` или человека проекта, а документы
печатают макрос. Строка инклуда вне макроса (например `\\setmainfont` в `fonts.tex.j2`) действует на весь документ,
который этот инклуд подключает. Разбор текстовый и не исполняет Jinja: он отвечает на вопрос «в каких документах
шаблона встречается поле», а не «что напечатается при этих значениях».
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

# Человек проекта хранится в собственном поле проекта, а не в project.meta.
PERSON_KEYS = ("supervisor", "co_supervisor", "academic_supervisor")

_META_REF = re.compile(
    r"project\.meta(?:\.get\(\s*['\"](?P<get>\w+)['\"]|\[\s*['\"](?P<item>\w+)['\"]\s*\]|\.(?P<attr>\w+))"
)
_PERSON_REF = re.compile(r"project\.(?P<person>" + "|".join(PERSON_KEYS) + r")\b")
_DEFINITION = re.compile(
    r"\\(?:newcommand|renewcommand|providecommand)\*?\s*\{?\\(?P<cmd>[A-Za-z@]+)|\\newif\\(?P<if>if[A-Za-z@]+)"
)
_MACRO_USE = re.compile(r"\\([A-Za-z@]+)")
_INPUT = re.compile(r"\\(?:input|include|subfile)\s*\{([^}]+)\}")


@dataclass(frozen=True)
class IncludeFields:
    """Разбор одного динамического инклуда: какие макросы печатают поле и какие поля действуют на весь документ."""

    macros: Mapping[str, frozenset[str]]
    whole: frozenset[str]


def referenced_keys(text: str) -> set[str]:
    """Ключи полей, на которые ссылается Jinja-текст: `project.meta.<ключ>` и люди проекта."""
    keys = {m.group("attr") or m.group("item") or m.group("get") for m in _META_REF.finditer(text)}
    keys.update(m.group("person") for m in _PERSON_REF.finditer(text))
    return {k for k in keys if k}


def parse_include(template_text: str) -> IncludeFields:
    """Ключ поля в макросы инклуда, которые его печатают, с учётом макросов, определённых через другие макросы.

    Тело `\\newcommand` читается до парной закрывающей скобки; флаг `\\newif\\ifX` печатает поля строк, где
    стоят его `\\Xtrue`/`\\Xfalse`. Поле в строке вне макросов действует на весь документ с этим инклудом.
    """
    parser = _IncludeParser()
    for line in strip_tex_comments(template_text).splitlines():
        parser.feed(line)
    return IncludeFields(macros=_keys_by_macro(parser.bodies), whole=frozenset(parser.whole))


class _IncludeParser:
    def __init__(self) -> None:
        self.bodies: dict[str, list[str]] = {}
        self.whole: set[str] = set()
        self._flags: set[str] = set()
        self._current: str | None = None
        self._depth = 0

    def feed(self, line: str) -> None:
        rest: str | None = line
        while rest:
            rest = self._top(rest) if self._current is None else self._body(self._current, rest)

    def _body(self, macro: str, line: str) -> str | None:
        end = _body_end(line, self._depth)
        if end is None:
            self._depth += _balance(line)
            self.bodies[macro].append(line)
            return None
        self.bodies[macro].append(line[:end])
        self._current = None
        return line[end:]

    def _top(self, line: str) -> str | None:
        found = _DEFINITION.search(line)
        head = line if found is None else line[: found.start()]
        owners = [f for f in self._flags if f"\\{f[2:]}true" in head or f"\\{f[2:]}false" in head]
        for flag in owners:
            self.bodies[flag].append(head)
        if not owners:
            self.whole |= referenced_keys(head)
        if found is None:
            return None
        flag = found.group("if")
        if flag:
            self._flags.add(flag)
            self.bodies.setdefault(flag, [])
            return line[found.end() :]
        self._current = found.group("cmd")
        self.bodies.setdefault(self._current, [])
        self._depth = 0
        return _ARGS_AFTER_NAME.sub("", line[found.end() :], count=1)


_ARGS_AFTER_NAME = re.compile(r"^\s*\}?\s*(?:\[[^\]]*\]\s*)*")


def _balance(text: str) -> int:
    opened = len(re.findall(r"(?<!\\)\{", text))
    closed = len(re.findall(r"(?<!\\)\}", text))
    return opened - closed


def _body_end(line: str, depth: int) -> int | None:
    """Конец тела макроса в строке: позиция после скобки, которая возвращает глубину к нулю."""
    opened = depth > 0
    for index, char in enumerate(line):
        if index > 0 and line[index - 1] == "\\":
            continue
        if char == "{":
            depth += 1
            opened = True
        elif char == "}":
            depth -= 1
        if opened and depth == 0:
            return index + 1
    return None


def _keys_by_macro(bodies: Mapping[str, list[str]]) -> dict[str, frozenset[str]]:
    direct = {macro: referenced_keys("\n".join(lines)) for macro, lines in bodies.items()}
    uses = {macro: set(_MACRO_USE.findall("\n".join(lines))) - {macro} for macro, lines in bodies.items()}
    # Макрос через другой макрос (`\\hseProjectNameEn` = `\\hseTitleEn`) печатает те же поля.
    changed = True
    while changed:
        changed = False
        for macro, used in uses.items():
            extra = set().union(*(direct.get(u, set()) for u in used)) - direct[macro] if used else set()
            if extra:
                direct[macro] |= extra
                changed = True
    by_key: dict[str, set[str]] = {}
    for macro, keys in direct.items():
        for key in keys:
            by_key.setdefault(key, set()).add(macro)
    return {key: frozenset(names) for key, names in by_key.items()}


def used_macros(text: str) -> set[str]:
    """Имена всех макросов, которые встречаются в тексте (без комментариев LaTeX)."""
    return set(_MACRO_USE.findall(strip_tex_comments(text)))


def input_targets(text: str) -> list[str]:
    """Аргументы `\\input`/`\\include`/`\\subfile` вне комментариев."""
    return [t.strip() for t in _INPUT.findall(strip_tex_comments(text))]


def strip_tex_comments(text: str) -> str:
    """Текст без комментариев: `%` до конца строки, кроме экранированного `\\%`."""
    return "\n".join(re.sub(r"(?<!\\)%.*", "", line) for line in text.splitlines())


def printed_keys(
    includes: Mapping[str, IncludeFields], doc_macros: Iterable[str], doc_inputs: Iterable[str], doc_text_keys: set[str]
) -> set[str]:
    """Поля, которые печатает документ.

    `includes` — разбор инклудов по пути их результата без расширения (`common/meta`), `doc_inputs` — пути
    подключённых документом инклудов в том же виде, `doc_text_keys` — ключи, на которые исходник документа ссылается
    сам (Jinja-исходник, отрендеренный при создании проекта).
    """
    macros = set(doc_macros)
    inputs = set(doc_inputs)
    keys = set(doc_text_keys)
    for output, parsed in includes.items():
        if output not in inputs:
            continue
        keys |= parsed.whole
        keys |= {key for key, names in parsed.macros.items() if names & macros}
    return keys
