"""Чистые функции над текстом: минимальные правки между версиями и трёхстороннее слияние по строкам.

Правки нужны, чтобы чужую версию файла (git, агент, другая вкладка) превратить в операции над общим текстом
комнаты, а не заменять его целиком: курсоры и несохранённый ввод участников остаются на месте.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

# Выше этого размера блока уточнение по символам не делаем: оно квадратично, а выигрыш для курсоров мал.
_CHAR_REFINE_MAX = 4000


@dataclass(frozen=True)
class TextEdit:
    """Заменить `old[start:end]` на `insert`; смещения в кодовых точках исходной строки."""

    start: int
    end: int
    insert: str


def _lines(text: str) -> list[str]:
    return text.splitlines(keepends=True)


def diff_edits(old: str, new: str) -> list[TextEdit]:
    """Правки от `old` к `new` по возрастанию смещений, без пересечений."""
    if old == new:
        return []
    a, b = _lines(old), _lines(new)
    offsets = [0]
    for line in a:
        offsets.append(offsets[-1] + len(line))
    b_offsets = [0]
    for line in b:
        b_offsets.append(b_offsets[-1] + len(line))
    edits: list[TextEdit] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        start, end = offsets[i1], offsets[i2]
        old_block, new_block = old[start:end], new[b_offsets[j1] : b_offsets[j2]]
        if tag == "replace" and 0 < len(old_block) <= _CHAR_REFINE_MAX and 0 < len(new_block) <= _CHAR_REFINE_MAX:
            edits.extend(_refine(old_block, new_block, start))
        else:
            edits.append(TextEdit(start, end, new_block))
    return edits


def _refine(old_block: str, new_block: str, base: int) -> list[TextEdit]:
    out: list[TextEdit] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, old_block, new_block, autojunk=False).get_opcodes():
        if tag != "equal":
            out.append(TextEdit(base + i1, base + i2, new_block[j1:j2]))
    return out


def apply_edits(text: str, edits: list[TextEdit]) -> str:
    """Применяет правки `diff_edits` (от конца к началу, смещения исходного текста)."""
    for edit in reversed(edits):
        text = text[: edit.start] + edit.insert + text[edit.end :]
    return text


@dataclass(frozen=True)
class MergeResult:
    text: str
    # Число участков, где обе стороны правили одно место по-разному; на них выбрана версия `ours`.
    conflicts: int


@dataclass(frozen=True)
class _Change:
    b1: int
    b2: int
    lines: tuple[str, ...]


def _changes(base: list[str], other: list[str]) -> list[_Change]:
    return [
        _Change(i1, i2, tuple(other[j1:j2]))
        for tag, i1, i2, j1, j2 in SequenceMatcher(None, base, other, autojunk=False).get_opcodes()
        if tag != "equal"
    ]


def _apply(base: list[str], lo: int, hi: int, changes: list[_Change]) -> list[str]:
    out: list[str] = []
    pos = lo
    for change in changes:
        out.extend(base[pos : change.b1])
        out.extend(change.lines)
        pos = change.b2
    out.extend(base[pos:hi])
    return out


def _clusters(tagged: list[tuple[_Change, str]]) -> list[list[tuple[_Change, str]]]:
    """Правки обеих сторон, сгруппированные в скопления: пересекающиеся и соприкасающиеся вставкой решаются вместе."""
    groups: list[list[tuple[_Change, str]]] = []
    hi = -1
    for item in tagged:
        change = item[0]
        if groups and _touches(groups[-1][0][0], change, hi):
            groups[-1].append(item)
            hi = max(hi, change.b2)
        else:
            groups.append([item])
            hi = change.b2
    return groups


def _touches(first: _Change, change: _Change, hi: int) -> bool:
    if change.b1 < hi:
        return True
    return change.b1 == hi and (change.b1 == change.b2 or first.b1 == first.b2)


def merge3(base: str, ours: str, theirs: str) -> MergeResult:
    """Слияние по строкам: правки обеих сторон относительно `base`. При споре за одно место берётся `ours`."""
    if theirs in (ours, base):
        return MergeResult(ours, 0)
    if ours == base:
        return MergeResult(theirs, 0)
    b, o, t = _lines(base), _lines(ours), _lines(theirs)
    tagged = sorted(
        [(c, "o") for c in _changes(b, o)] + [(c, "t") for c in _changes(b, t)], key=lambda x: (x[0].b1, x[0].b2)
    )
    result: list[str] = []
    conflicts = 0
    pos = 0
    for cluster in _clusters(tagged):
        lo = min(c.b1 for c, _ in cluster)
        hi = max(c.b2 for c, _ in cluster)
        result.extend(b[pos:lo])
        mine = [c for c, who in cluster if who == "o"]
        other = [c for c, who in cluster if who == "t"]
        ours_part, theirs_part = _apply(b, lo, hi, mine), _apply(b, lo, hi, other)
        if mine and other and ours_part != theirs_part:
            conflicts += 1
        result.extend(ours_part if mine else theirs_part)
        pos = hi
    result.extend(b[pos:])
    return MergeResult("".join(result), conflicts)
