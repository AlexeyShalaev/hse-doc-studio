r"""Точечные правки YAML пака по позициям узлов (docs/design/template-studio.md, D11, срез T4).

Файлы пака густо комментированы и выровнены (`label:       { ru: ... }`), поэтому форма Студии шаблонов не
переписывает файл целиком, а меняет только фрагмент затронутого узла. Позиции узлов даёт `yaml.compose`
(`start_mark`, `end_mark`); остальной текст, комментарии, порядок ключей и стиль строк остаются байт в байт.

Операции (путь это кортеж ключей словарей и индексов списков):

* `set_value`: значение по пути. Скаляр заменяется в своём стиле (простой, в кавычках, блочный `|`); словарь и
  список правятся поэлементно; отсутствующий последний ключ дописывается в конец своего блока с отступом соседей
  (и с их выравниванием значений). Значение, равное текущему, ничего не меняет;
* `insert_item`: элемент списка по индексу (`len` дописывает в конец);
* `delete`: ключ словаря или элемент списка вместе с комментарием над ним;
* `move_item`: элемент списка на новое место, с его комментарием.

Каждая правка проверяет себя: результат разбирается безопасным загрузчиком ровно в ожидаемые данные (та же правка
над разобранным исходником), иначе `YamlEditError`, а текст остаётся прежним. Якоря и ссылки (`&`, `*`) не
поддерживаются: в паках их нет.
"""

from __future__ import annotations

import bisect
import copy
from dataclasses import dataclass
from typing import Any

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

Key = str | int
YamlPath = tuple[Key, ...]

# Быстрый разбор libyaml, если он есть: правка разбирает файл несколько раз. Позиции узлов у него те же, что у
# чистого PyYAML (индекс в символах), простой стиль скаляра пишется как "" вместо None.
_LOADER: Any = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
# Ширина строки эмиттера PyYAML: без переносов длинных строк в кавычках.
_NO_WRAP = 2**31 - 1
# Новое значение-словарь или список пишется в одну строку (`{ page: 1, x_mm: 80 }`), если оно не длиннее этого.
_INLINE_MAX = 100


class YamlEditError(ValueError):
    """Правку нельзя применить: пути нет, узел не того вида или результат читается не в ожидаемые данные."""


# ---------------------------------------------------------------------------
# Публичные операции
# ---------------------------------------------------------------------------


def set_value(text: str, path: YamlPath, value: Any) -> str:
    """Значение по пути; последний ключ словаря может отсутствовать, тогда он дописывается в конец блока."""
    expected = _expect(text, path, lambda parent, key: _assign(parent, key, value), root=value)
    return _checked(_set(text, path, value), expected)


def insert_item(text: str, path: YamlPath, index: int, value: Any) -> str:
    """Новый элемент списка по пути на место `index` (от 0 до длины списка)."""
    expected = _expect(text, (*path, index), lambda parent, key: _insert_into(parent, key, value))
    return _checked(_insert(text, path, index, value), expected)


def delete(text: str, path: YamlPath) -> str:
    """Ключ словаря или элемент списка по пути, со строками узла и комментарием над ним."""
    if not path:
        raise YamlEditError("the document root cannot be deleted")
    expected = _expect(text, path, _remove_from)
    return _checked(_delete(text, path), expected)


def move_item(text: str, path: YamlPath, src: int, dst: int) -> str:
    """Элемент списка по пути с места `src` на место `dst` (индекс в итоговом списке)."""
    expected = _expect(text, (*path, src), lambda parent, key: _move_within(parent, key, dst))
    return _checked(_move(text, path, src, dst), expected)


# ---------------------------------------------------------------------------
# Ожидаемые данные: та же правка над разобранным документом
# ---------------------------------------------------------------------------


def _load(text: str) -> Any:
    try:
        return yaml.load(text, Loader=_LOADER)  # noqa: S506 — безопасный загрузчик (SafeLoader или CSafeLoader)
    except yaml.YAMLError as exc:
        raise YamlEditError(f"the document is not valid YAML: {exc}") from exc


def _expect(text: str, path: YamlPath, change: Any, root: Any = None) -> Any:
    data = copy.deepcopy(_load(text))
    if data is None:
        data = {}
    if not path:
        return root
    parent = data
    for key in path[:-1]:
        parent = _child(parent, key)
    change(parent, path[-1])
    return data


def _child(container: Any, key: Key) -> Any:
    if isinstance(container, dict) and isinstance(key, str) and key in container:
        return container[key]
    if isinstance(container, list) and isinstance(key, int) and 0 <= key < len(container):
        return container[key]
    raise YamlEditError(f"path element {key!r} is not in the document")


def _assign(parent: Any, key: Key, value: Any) -> None:
    if isinstance(parent, dict) and isinstance(key, str):
        parent[key] = value
        return
    _child(parent, key)
    parent[key] = value


def _insert_into(parent: Any, index: Key, value: Any) -> None:
    if not isinstance(parent, list) or not isinstance(index, int) or not 0 <= index <= len(parent):
        raise YamlEditError(f"cannot insert at {index!r}: not a list or the index is out of range")
    parent.insert(index, value)


def _remove_from(parent: Any, key: Key) -> None:
    _child(parent, key)
    del parent[key]


def _move_within(parent: Any, src: Key, dst: int) -> None:
    item = _child(parent, src)
    if not isinstance(parent, list) or not isinstance(src, int) or not 0 <= dst < len(parent):
        raise YamlEditError(f"cannot move to {dst}: not a list or the index is out of range")
    parent.pop(src)
    parent.insert(dst, item)


def _same(a: Any, b: Any) -> bool:
    """Равенство с типами: `True` не равно `1`, дата не равна строке."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b, strict=True))
    return bool(a == b)


def _checked(text: str, expected: Any) -> str:
    if not _same(_load(text), expected):
        raise YamlEditError("the edited document does not read back as intended")
    return text


# ---------------------------------------------------------------------------
# Документ и позиции
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Loc:
    node: Node | None
    parent: Node | None  # словарь или список, в котором лежит узел; None у корня
    index: int  # номер пары словаря или элемента списка; -1 у корня
    in_flow: bool  # узел внутри однострочной коллекции (`{...}`, `[...]`)


class _Doc:
    def __init__(self, text: str) -> None:
        self.text = text
        try:
            self.root: Node | None = yaml.compose(text, Loader=_LOADER)
        except yaml.YAMLError as exc:
            raise YamlEditError(f"the document is not valid YAML: {exc}") from exc
        self.line_starts = [0, *(i + 1 for i, ch in enumerate(text) if ch == "\n")]

    def line_of(self, pos: int) -> int:
        return bisect.bisect_right(self.line_starts, pos) - 1

    def line_end(self, line: int) -> int:
        """Начало следующей строки (или конец текста)."""
        return self.line_starts[line + 1] if line + 1 < len(self.line_starts) else len(self.text)

    def column(self, pos: int) -> int:
        return pos - self.line_starts[self.line_of(pos)]

    def line_text(self, line: int) -> str:
        return self.text[self.line_starts[line] : self.line_end(line)]

    def is_blank(self, line: int) -> bool:
        return 0 <= line < len(self.line_starts) and not self.line_text(line).strip()

    def is_comment_at(self, line: int, col: int) -> bool:
        raw = self.line_text(line)
        body = raw.lstrip(" ")
        return body.startswith("#") and len(raw) - len(body) == col

    def quote_style(self) -> str:
        """Кавычки, которых в файле больше: двойные или одинарные."""
        counts = {'"': 0, "'": 0}
        stack = [self.root] if self.root is not None else []
        while stack:
            node = stack.pop()
            if isinstance(node, ScalarNode) and node.style in counts:
                counts[node.style] += 1
            elif isinstance(node, MappingNode):
                stack.extend(part for pair in node.value for part in pair)
            elif isinstance(node, SequenceNode):
                stack.extend(node.value)
        return "'" if counts["'"] > counts['"'] else '"'

    def is_flow(self, node: Node) -> bool:
        return isinstance(node, MappingNode | SequenceNode) and self.text[node.start_mark.index] in "[{"

    def end(self, node: Node) -> int:
        """Конец содержимого узла: без хвостовых пустых строк блочного скаляра и без комментариев за ним."""
        if isinstance(node, ScalarNode):
            start, stop = node.start_mark.index, node.end_mark.index
            return start + len(self.text[start:stop].rstrip())
        if self.is_flow(node) or not node.value:
            return int(node.end_mark.index)
        last = node.value[-1]
        if isinstance(node, MappingNode):
            return max(self.end(last[0]), self.end(last[1]))
        return self.end(last)

    def dash(self, item: Node) -> int:
        """Позиция `-` элемента блочного списка."""
        i = item.start_mark.index - 1
        while i >= 0 and self.text[i] in " \n":
            i -= 1
        if i < 0 or self.text[i] != "-":
            raise YamlEditError("cannot find the dash of a block list item")
        return i

    def entry_start(self, coll: Node, index: int) -> int:
        if isinstance(coll, MappingNode):
            return int(coll.value[index][0].start_mark.index)
        return self.dash(coll.value[index])

    def entry_end(self, coll: Node, index: int) -> int:
        entry = coll.value[index]
        return max(self.end(entry[0]), self.end(entry[1])) if isinstance(coll, MappingNode) else self.end(entry)

    def entry_lines(self, coll: Node, index: int) -> tuple[int, int]:
        """Первая и последняя строка элемента блочной коллекции; комментарий прямо над ним входит в элемент."""
        start = self.entry_start(coll, index)
        col = self.column(start)
        first = self.line_of(start)
        while first > 0 and self.is_comment_at(first - 1, col):
            first -= 1
        stop = self.entry_end(coll, index)
        last = self.line_of(stop - 1) if stop > start else self.line_of(start)
        return first, last

    def separated(self, coll: Node) -> bool:
        """Элементы разделены пустыми строками (как поля `meta_fields`): новый элемент получит такую же."""
        spans = [self.entry_lines(coll, i) for i in range(len(coll.value))]
        if len(spans) < 2:
            return False
        return all(
            any(self.is_blank(line) for line in range(prev[1] + 1, cur[0]))
            for prev, cur in zip(spans, spans[1:], strict=False)
        )

    def locate(self, path: YamlPath) -> _Loc:
        loc = _Loc(self.root, None, -1, False)
        for key in path:
            loc = self._step(loc, key)
        return loc

    def _step(self, loc: _Loc, key: Key) -> _Loc:
        node = loc.node
        in_flow = loc.in_flow or (node is not None and self.is_flow(node))
        if isinstance(node, MappingNode) and isinstance(key, str):
            for i, (k, v) in enumerate(node.value):
                if isinstance(k, ScalarNode) and k.value == key:
                    return _Loc(v, node, i, in_flow)
        elif isinstance(node, SequenceNode) and isinstance(key, int) and 0 <= key < len(node.value):
            return _Loc(node.value[key], node, key, in_flow)
        raise YamlEditError(f"path element {key!r} is not in the document")


# ---------------------------------------------------------------------------
# Текст новых значений
# ---------------------------------------------------------------------------


def _reads_back(candidate: str, value: Any, *, flow: bool, as_key: bool) -> bool:
    if as_key:
        probe = f"{{{candidate}: 0}}" if flow else f"{candidate}: 0\n"
    else:
        probe = f"[{candidate}]" if flow else f"k: {candidate}\n"
    try:
        loaded = yaml.load(probe, Loader=_LOADER)  # noqa: S506 — безопасный загрузчик
    except yaml.YAMLError:
        return False
    if as_key:
        return isinstance(loaded, dict) and len(loaded) == 1 and _same(next(iter(loaded)), value)
    if flow:
        return isinstance(loaded, list) and len(loaded) == 1 and _same(loaded[0], value)
    return isinstance(loaded, dict) and list(loaded) == ["k"] and _same(loaded["k"], value)


def _dumped(value: Any, style: str | None) -> str | None:
    text = yaml.safe_dump(value, default_style=style, allow_unicode=True, width=_NO_WRAP)
    text = text.removesuffix("\n...\n").removesuffix("\n")
    return None if "\n" in text else text


def _scalar_candidates(value: Any, style: str | None, *, plain_first: bool) -> list[str]:
    """Записи скаляра по порядку предпочтения: простой (если стиль простой или кавычки были вынужденными),
    затем стиль узла, затем одинарные и двойные кавычки."""
    if not isinstance(value, str):
        dumped = _dumped(value, None)
        return [dumped] if dumped is not None else []
    one_line = "\n" not in value
    single = "'" + value.replace("'", "''") + "'" if one_line else None
    double = _dumped(value, '"')
    quoted = [double, single] if style == '"' else [single, double]
    plain = value if value and one_line and (style is None or plain_first) else None
    return [text for text in (plain, *quoted) if text is not None]


def _scalar_text(
    value: Any, style: str | None = None, *, flow: bool = False, as_key: bool = False, plain_first: bool = False
) -> str:
    for candidate in _scalar_candidates(value, style, plain_first=plain_first):
        if _reads_back(candidate, value, flow=flow, as_key=as_key):
            return candidate
    raise YamlEditError(f"cannot write {value!r} as a YAML scalar")


def _quotes_forced(node: Node, *, flow: bool) -> bool:
    """Кавычки узла вынужденные: его значение простым скаляром в этом месте не записать (`"2027"`, `'a, b'`)."""
    if not isinstance(node, ScalarNode) or node.style not in ("'", '"'):
        return False
    value = node.value
    return not value or "\n" in value or not _reads_back(value, value, flow=flow, as_key=False)


def _literal(value: str, indent: int) -> str | None:
    """Блочный скаляр `|` с содержимым на отступе `indent`; None, если строку так не записать."""
    body = value.rstrip("\n")
    trailing = len(value) - len(body)
    if not body or body[0] in " \t" or trailing > 1:
        return None
    chomp = "" if trailing else "-"
    pad = " " * indent
    return "|" + chomp + "".join("\n" + (pad + line if line else "") for line in body.split("\n"))


def _fits_inline(value: Any) -> bool:
    if isinstance(value, dict):
        return all(not isinstance(v, dict) and _fits_inline(v) for v in value.values())
    if isinstance(value, list):
        return all(not isinstance(v, dict) and _fits_inline(v) for v in value)
    return True


def _flow_text(value: Any) -> str:
    if isinstance(value, dict):
        if not value:
            return "{}"
        pairs = (f"{_scalar_text(k, flow=True, as_key=True)}: {_flow_text(v)}" for k, v in value.items())
        return "{ " + ", ".join(pairs) + " }"
    if isinstance(value, list):
        return "[" + ", ".join(_flow_text(v) for v in value) + "]"
    return _scalar_text(value, flow=True)


def _inline(
    value: Any, *, flow: bool, style: str | None = None, literal_indent: int | None = None, plain_first: bool = False
) -> str | None:
    """Значение одной строкой (скаляр или `{...}`, `[...]`) или блочный скаляр; None, если нужен блок строк."""
    if isinstance(value, dict | list):
        if flow:
            return _flow_text(value)
        if not value:
            return "{}" if isinstance(value, dict) else "[]"
        text = _flow_text(value) if _fits_inline(value) else None
        return text if text is not None and len(text) <= _INLINE_MAX else None
    if flow:
        return _scalar_text(value, None if style in ("|", ">") else style, flow=True, plain_first=plain_first)
    if style in ("|", ">") and isinstance(value, str) and literal_indent is not None:
        literal = _literal(value, literal_indent)
        if literal is not None:
            return literal
        style = '"'
    return _scalar_text(value, style, plain_first=plain_first)


def _entry_lines(key: Any, value: Any, indent: int, align: int | None = None) -> list[str]:
    head = " " * indent + _scalar_text(key, as_key=True) + ":"
    inline = _inline(value, flow=False, literal_indent=indent + 2)
    if inline is not None:
        gap = max(1, align - len(head)) if align is not None else 1
        return [head + " " * gap + inline + "\n"]
    return [head + "\n", *_block_lines(value, indent + 2)]


def _item_lines(value: Any, indent: int) -> list[str]:
    pad = " " * indent
    inline = _inline(value, flow=False, literal_indent=indent + 2)
    if inline is not None:
        return [f"{pad}- {inline}\n"]
    body = _block_lines(value, indent + 2)
    if isinstance(value, dict):
        return [pad + "- " + body[0][indent + 2 :], *body[1:]]
    return [f"{pad}-\n", *body]


def _block_lines(value: Any, indent: int) -> list[str]:
    if isinstance(value, dict):
        return [line for k, v in value.items() for line in _entry_lines(k, v, indent)]
    return [line for item in value for line in _item_lines(item, indent)]


# ---------------------------------------------------------------------------
# Правки текста
# ---------------------------------------------------------------------------


def _splice(text: str, start: int, stop: int, new: str) -> str:
    return text[:start] + new + text[stop:]


def _block_insert(doc: _Doc, coll: Node, index: int, lines: list[str], separated: bool) -> str:
    blank = ["\n"] if separated else []
    if index < len(coll.value):
        first, _ = doc.entry_lines(coll, index)
        pos = doc.line_starts[first]
        return _splice(doc.text, pos, pos, "".join([*lines, *blank]))
    _, last = doc.entry_lines(coll, len(coll.value) - 1)
    pos = doc.line_end(last)
    lead = "\n" if pos == len(doc.text) and not doc.text.endswith("\n") else ""
    return _splice(doc.text, pos, pos, lead + "".join([*blank, *lines]))


def _block_remove(doc: _Doc, coll: Node, index: int, separated: bool) -> tuple[str, str]:
    """Текст без элемента и сами строки элемента (с комментарием над ним, без разделяющей пустой строки)."""
    first, last = doc.entry_lines(coll, index)
    start, stop = doc.line_starts[first], doc.line_end(last)
    removed = doc.text[start:stop]
    if separated:
        if index < len(coll.value) - 1 and doc.is_blank(last + 1):
            stop = doc.line_end(last + 1)
        elif index > 0 and doc.is_blank(first - 1):
            start = doc.line_starts[first - 1]
    return _splice(doc.text, start, stop, ""), removed


def _flow_spans(doc: _Doc, coll: Node) -> list[tuple[int, int]]:
    return [
        (int((entry[0] if isinstance(coll, MappingNode) else entry).start_mark.index), doc.entry_end(coll, i))
        for i, entry in enumerate(coll.value)
    ]


def _flow_insert(doc: _Doc, coll: Node, index: int, item: str) -> str:
    spans = _flow_spans(doc, coll)
    if not spans:
        opening, closing = coll.start_mark.index, coll.end_mark.index - 1
        inner = f" {item} " if isinstance(coll, MappingNode) else item
        return _splice(doc.text, opening + 1, closing, inner)
    if index < len(spans):
        pos = spans[index][0]
        return _splice(doc.text, pos, pos, f"{item}, ")
    pos = spans[-1][1]
    return _splice(doc.text, pos, pos, f", {item}")


def _flow_remove(doc: _Doc, coll: Node, index: int) -> tuple[str, str]:
    spans = _flow_spans(doc, coll)
    removed = doc.text[spans[index][0] : spans[index][1]]
    if len(spans) == 1:
        start, stop = coll.start_mark.index + 1, coll.end_mark.index - 1
    elif index < len(spans) - 1:
        start, stop = spans[index][0], spans[index + 1][0]
    else:
        start, stop = spans[index - 1][1], spans[index][1]
    return _splice(doc.text, start, stop, ""), removed


def _after_indicator(doc: _Doc, loc: _Loc) -> int:
    """Позиция сразу за `:` ключа или `-` элемента, после которых стоит значение узла."""
    if isinstance(loc.parent, MappingNode):
        colon = doc.text.find(":", doc.end(loc.parent.value[loc.index][0]))
        if colon < 0:
            raise YamlEditError("cannot find the colon of a mapping key")
        return colon + 1
    if isinstance(loc.parent, SequenceNode):
        return doc.dash(loc.parent.value[loc.index]) + 1
    return 0


def _child_indent(doc: _Doc, loc: _Loc) -> int:
    if isinstance(loc.parent, MappingNode):
        return doc.column(loc.parent.value[loc.index][0].start_mark.index) + 2
    if isinstance(loc.parent, SequenceNode):
        return doc.column(doc.dash(loc.parent.value[loc.index])) + 2
    return 0


def _literal_indent(doc: _Doc, node: Node | None, default: int) -> int:
    """Отступ содержимого существующего блочного скаляра; у прочих узлов `default`."""
    if not isinstance(node, ScalarNode) or node.style not in ("|", ">"):
        return default
    header = doc.line_of(node.start_mark.index)
    for line in range(header + 1, doc.line_of(max(doc.end(node) - 1, node.start_mark.index)) + 1):
        raw = doc.line_text(line)
        if raw.strip():
            return len(raw) - len(raw.lstrip(" "))
    return default


def _bare_key_end(doc: _Doc, loc: _Loc) -> int | None:
    """Конец ключа без значения и без двоеточия (`{ a, b: c }`): значение дописывается за ним."""
    node = loc.node
    if not isinstance(node, ScalarNode) or not isinstance(loc.parent, MappingNode):
        return None
    key_end = doc.end(loc.parent.value[loc.index][0])
    empty = node.start_mark.index == node.end_mark.index
    return key_end if empty and ":" not in doc.text[key_end : node.start_mark.index] else None


def _replace(doc: _Doc, loc: _Loc, value: Any) -> str:
    """Узел целиком заменяется новым значением (смена вида узла или пустая коллекция)."""
    node, text = loc.node, doc.text
    if node is None or loc.parent is None:
        inline = _inline(value, flow=False)
        return (inline + "\n") if inline is not None else "".join(_block_lines(value, 0))
    indent = 0 if loc.in_flow else _child_indent(doc, loc)
    style = (node.style or None) if isinstance(node, ScalarNode) else None  # libyaml пишет простой стиль как ""
    plain = style is None
    if plain:
        # Простому скаляру, которому теперь нужны кавычки, достаются кавычки, преобладающие в файле.
        style = doc.quote_style()
    inline = _inline(
        value,
        flow=loc.in_flow,
        style=style,
        literal_indent=_literal_indent(doc, node, indent),
        plain_first=plain or _quotes_forced(node, flow=loc.in_flow),
    )
    block_node = isinstance(node, MappingNode | SequenceNode) and not doc.is_flow(node)
    bare_key = _bare_key_end(doc, loc)
    if inline is not None and bare_key is not None:
        return _splice(text, bare_key, bare_key, ": " + inline)
    if inline is not None and not block_node:
        return _splice(text, node.start_mark.index, doc.end(node), inline)
    start, stop = _after_indicator(doc, loc), doc.end(node)
    if inline is not None:
        return _splice(text, start, stop, " " + inline)
    body = "".join(_block_lines(value, indent)).removesuffix("\n")
    if isinstance(loc.parent, SequenceNode) and isinstance(value, dict):
        return _splice(text, start, stop, " " + body[indent:])
    return _splice(text, start, stop, "\n" + body)


def _align_column(doc: _Doc, mapping: Node) -> int | None:
    """Колонка выровненных значений блока (`label:       { ... }`), если у всех пар она одна и есть выравнивание."""
    columns: set[int] = set()
    padded = False
    for key, value in mapping.value:
        start = value.start_mark.index
        if doc.line_of(key.start_mark.index) != doc.line_of(start) or start == doc.end(value):
            return None  # значение блоком на следующих строках или пустое: выравнивать не по чему
        col = doc.column(start)
        # `key: value` даёт разницу в 2 (двоеточие и пробел); больше значит выравнивание пробелами.
        padded = padded or col - doc.column(doc.end(key)) > 2
        columns.add(col)
    return columns.pop() if padded and len(columns) == 1 else None


def _add_key(doc: _Doc, loc: _Loc, key: Key, value: Any) -> str:
    mapping = loc.node
    if not isinstance(key, str):
        raise YamlEditError(f"path element {key!r} is not in the document")
    if mapping is None and loc.parent is None:
        return "".join(_entry_lines(key, value, 0))
    if not isinstance(mapping, MappingNode):
        raise YamlEditError(f"cannot add key {key!r}: the parent is not a mapping")
    if loc.in_flow or doc.is_flow(mapping):
        item = f"{_scalar_text(key, flow=True, as_key=True)}: {_inline(value, flow=True)}"
        return _flow_insert(doc, mapping, len(mapping.value), item)
    indent = doc.column(mapping.value[0][0].start_mark.index)
    lines = _entry_lines(key, value, indent, _align_column(doc, mapping))
    return _block_insert(doc, mapping, len(mapping.value), lines, doc.separated(mapping))


def _current(text: str, path: YamlPath) -> Any:
    node = _load(text)
    for key in path:
        node = _child(node, key)
    return node


def _set(text: str, path: YamlPath, value: Any) -> str:
    current = _missing = object()
    try:
        current = _current(text, path)
    except YamlEditError:
        if not path:
            raise
    if current is not _missing and _same(current, value):
        return text
    doc = _Doc(text)
    if current is _missing:
        return _add_key(doc, doc.locate(path[:-1]), path[-1], value)
    if isinstance(value, dict) and isinstance(current, dict) and current and value:
        return _set_mapping(text, path, current, value)
    if isinstance(value, list) and isinstance(current, list) and current and value:
        return _set_sequence(text, path, current, value)
    return _replace(doc, doc.locate(path), value)


def _set_mapping(text: str, path: YamlPath, current: dict[Any, Any], value: dict[Any, Any]) -> str:
    """Словарь правится по ключам: лишние удаляются, изменённые правятся на месте, новые дописываются."""
    for key in [k for k in current if k not in value]:
        text = _delete(text, (*path, key))
    for key, item in value.items():
        if key not in current or not _same(current[key], item):
            text = _set(text, (*path, key), item)
    return text


def _set_sequence(text: str, path: YamlPath, current: list[Any], value: list[Any]) -> str:
    """Список правится по элементам: общие на месте, лишние с конца удаляются, новые дописываются."""
    for i in range(min(len(current), len(value))):
        if not _same(current[i], value[i]):
            text = _set(text, (*path, i), value[i])
    for i in reversed(range(len(value), len(current))):
        text = _delete(text, (*path, i))
    for i in range(len(current), len(value)):
        text = _insert(text, path, i, value[i])
    return text


def _sequence(doc: _Doc, path: YamlPath) -> tuple[_Loc, SequenceNode]:
    loc = doc.locate(path)
    if not isinstance(loc.node, SequenceNode):
        raise YamlEditError(f"{list(path)} is not a list")
    return loc, loc.node


def _insert(text: str, path: YamlPath, index: int, value: Any) -> str:
    doc = _Doc(text)
    loc, seq = _sequence(doc, path)
    if not 0 <= index <= len(seq.value):
        raise YamlEditError(f"index {index} is out of range for a list of {len(seq.value)}")
    if loc.in_flow or doc.is_flow(seq):
        if not seq.value and not loc.in_flow and _inline([value], flow=False) is None:
            return _replace(doc, loc, [value])
        return _flow_insert(doc, seq, index, _flow_text(value))
    indent = doc.column(doc.dash(seq.value[0]))
    if isinstance(value, dict | list) and all(doc.is_flow(item) for item in seq.value):
        # Соседи записаны одной строкой (`- { doc_id: ..., when: { ... } }`): новый элемент так же.
        lines = [" " * indent + "- " + _flow_text(value) + "\n"]
    else:
        lines = _item_lines(value, indent)
    return _block_insert(doc, seq, index, lines, doc.separated(seq))


def _delete(text: str, path: YamlPath) -> str:
    doc = _Doc(text)
    loc = doc.locate(path)
    parent = loc.parent
    if parent is None:
        raise YamlEditError("the document root cannot be deleted")
    if loc.in_flow:
        return _flow_remove(doc, parent, loc.index)[0]
    if len(parent.value) == 1:
        return _replace(doc, doc.locate(path[:-1]), {} if isinstance(parent, MappingNode) else [])
    start = doc.entry_start(parent, loc.index)
    if loc.index == 0 and doc.text[doc.line_starts[doc.line_of(start)] : start].strip():
        # Первый ключ словаря-элемента списка стоит на строке с `-`: следующий ключ поднимается на его место.
        first, _ = doc.entry_lines(parent, 1)
        stop = doc.line_starts[first] + doc.column(doc.entry_start(parent, 1))
        return _splice(doc.text, start, stop, "")
    return _block_remove(doc, parent, loc.index, doc.separated(parent))[0]


def _move(text: str, path: YamlPath, src: int, dst: int) -> str:
    doc = _Doc(text)
    loc, seq = _sequence(doc, path)
    if not (0 <= src < len(seq.value) and 0 <= dst < len(seq.value)):
        raise YamlEditError(f"cannot move {src} to {dst} in a list of {len(seq.value)}")
    if src == dst:
        return text
    if loc.in_flow or doc.is_flow(seq):
        # Тексты элементов переставляются по своим местам: разделители (`a,b, c`) остаются как были.
        spans = _flow_spans(doc, seq)
        items = [text[start:stop] for start, stop in spans]
        items.insert(dst, items.pop(src))
        for (start, stop), item in reversed(list(zip(spans, items, strict=True))):
            text = _splice(text, start, stop, item)
        return text
    separated = doc.separated(seq)
    rest, lines = _block_remove(doc, seq, src, separated)
    rest_doc = _Doc(rest)
    return _block_insert(rest_doc, _sequence(rest_doc, path)[1], dst, [lines], separated)
