"""Списки в фейках: те же правила, что у SQL (`infra/db/listing.py`). Подстрока без учёта регистра,
порядок по полю с пустыми значениями в конце и вторичным ключом, окно страницы и общее число."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from hse_doc_studio.core.listing import Found, Picked, SortKey, Window


def matches(q: str | None, *values: str | None) -> bool:
    if not q:
        return True
    needle = q.lower()
    return any(needle in (v or "").lower() for v in values)


def ordered[T](
    rows: Sequence[T], sort: SortKey, keys: Mapping[str, Callable[[T], Any]], tiebreak: Callable[[T], Any]
) -> list[T]:
    """Устойчивая двухпроходная сортировка: сначала вторичный ключ, затем поле (пустые всегда в конце)."""
    key = keys[sort.field]
    by_tie = sorted(rows, key=tiebreak)
    present = [r for r in by_tie if key(r) is not None]
    missing = [r for r in by_tie if key(r) is None]
    return sorted(present, key=key, reverse=sort.descending) + missing


def page[T](rows: list[T], window: Window) -> Found[T]:
    return Found(rows[window.offset : window.offset + window.limit], len(rows))


def picked[T](rows: list[T], limit: int) -> Picked[T]:
    return Picked(rows[:limit], len(rows) > limit)
