"""Общие формы списков админки: порядок, окно страницы, срез с общим числом и ответ пикера.

Поиск, фильтры, порядок и окно применяет хранилище (SQL), а не вызывающий код: списки могут быть большими.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 200
PICKER_LIMIT = 20


@dataclass(frozen=True)
class SortOrder:
    """Одно поле порядка; вторичный ключ `id` для устойчивого порядка добавляет хранилище."""

    field: str
    descending: bool = False


@dataclass(frozen=True)
class Window:
    limit: int = DEFAULT_PAGE_LIMIT
    offset: int = 0


@dataclass(frozen=True)
class Paged[T]:
    """Срез страницы и общее число записей под теми же фильтрами."""

    items: tuple[T, ...]
    total: int


@dataclass(frozen=True)
class PickerItem:
    kind: str
    id: str
    name: str
    detail: str | None = None


@dataclass(frozen=True)
class PickerResult:
    """Первые совпадения поиска; `has_more` просит уточнить запрос, страниц у пикера нет."""

    items: tuple[PickerItem, ...]
    has_more: bool


def clamp_limit(limit: int, maximum: int = MAX_PAGE_LIMIT) -> int:
    return max(1, min(limit, maximum))
