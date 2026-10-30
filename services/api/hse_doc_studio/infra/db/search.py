"""Поиск и порядок в списках админки: подстрока без учёта регистра и порядок со вторичным ключом."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import ColumnElement, false, or_
from sqlalchemy.sql.elements import UnaryExpression

from hse_doc_studio.core.listing import SortOrder

ESCAPE = "\\"


def contains_pattern(q: str) -> str:
    """Шаблон LIKE для подстроки: `%`, `_` и `\\` в запросе ищутся буквально."""
    escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def matches_any(q: str, columns: Sequence[Any]) -> ColumnElement[bool]:
    """Подстрока `q` в любом из столбцов, без учёта регистра (ILIKE)."""
    if not columns:
        return false()
    pattern = contains_pattern(q)
    return or_(*(column.ilike(pattern, escape=ESCAPE) for column in columns))


def ordered(
    sort: SortOrder,
    keys: Mapping[str, Sequence[Any]],
    tiebreak: Any,
    *,
    nullable: frozenset[str] = frozenset(),
) -> list[UnaryExpression[Any]]:
    """ORDER BY по полю из `keys` в нужную сторону и `tiebreak` по возрастанию для устойчивого порядка.

    У полей из `nullable` пустые значения в конце в обе стороны. У остальных NULLS не указывается: так
    порядок совпадает с индексом `(столбец DESC)` и страница читается по нему без сортировки таблицы.
    """
    order: list[UnaryExpression[Any]] = []
    for column in keys[sort.field]:
        directed = column.desc() if sort.descending else column.asc()
        order.append(directed.nulls_last() if sort.field in nullable else directed)
    order.append(tiebreak.asc())
    return order
