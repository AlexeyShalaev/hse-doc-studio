"""SQL-часть серверных списков: подстрока ILIKE, порядок по разрешённому полю и страница с COUNT(*)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import ColumnElement, Row, Select, UnaryExpression, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from hse_doc_studio.core.listing import SortKey, Window, like_escaped

# Колонка модели или выражение над ней (`lower(name)`, подзапрос-счётчик).
type Expr = ColumnElement[Any] | InstrumentedAttribute[Any]


def contains(q: str, *columns: Expr) -> ColumnElement[bool]:
    """Подстрока `q` без учёта регистра хотя бы в одной из колонок; `%`, `_` и `\\` ищутся буквально."""
    return contains_lower(q, *(func.lower(column) for column in columns))


def contains_lower(q: str, *expressions: Expr) -> ColumnElement[bool]:
    """То же для выражений, уже приведённых к нижнему регистру (`lower(name)`, `email_normalized`):
    условие совпадает с выражением индекса и может идти по нему."""
    pattern = like_escaped(q.lower())
    return or_(*(expression.like(pattern, escape="\\") for expression in expressions))


def ordering(sort: SortKey, columns: Mapping[str, Expr], *tiebreak: Expr) -> list[UnaryExpression[Any]]:
    """ORDER BY по полю из `columns` и вторичным ключам; пустые значения в конце при любом направлении."""
    column = columns[sort.field]
    head = (column.desc() if sort.descending else column.asc()).nulls_last()
    return [head, *(key.asc() for key in tiebreak)]


async def fetch_page[*Ts](session: AsyncSession, stmt: Select[*Ts], window: Window) -> tuple[Sequence[Row[*Ts]], int]:
    """Строки окна и COUNT(*) под тем же фильтром (без ORDER BY, LIMIT и OFFSET)."""
    total = (
        await session.execute(select(func.count()).select_from(stmt.order_by(None).limit(None).subquery()))
    ).scalar_one()
    rows = (await session.execute(stmt.limit(window.limit).offset(window.offset))).all()
    return rows, int(total)
