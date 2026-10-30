"""Общие формы админ-API: страница списка, её параметры, сортировка, поиск и пикер.

Списки ищут, фильтруют, сортируют и листают только на сервере. Нарушение параметров даёт 422 от FastAPI:
`limit` 1..200, `offset` от 0, `q` до 200 символов, `sort` одно поле из разрешённых ресурсом (`-` значит
по убыванию).
"""

# Без `from __future__ import annotations`: FastAPI читает аннотации зависимости `sort_param`, а шаблон
# в них берётся из замыкания, которого нет в глобальных именах модуля.

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Query
from pydantic import BaseModel, ConfigDict

from hse_doc_studio.core.listing import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    PICKER_LIMIT,
    SEARCH_MAX,
    SortKey,
    Window,
    search_text,
)

MAX_PAGE_SIZE = MAX_LIMIT
DEFAULT_PAGE_SIZE = DEFAULT_LIMIT


class Page[T](BaseModel):
    """Страница списка: срез `items` и общее число записей `total` под тем же фильтром."""

    model_config = ConfigDict(extra="forbid")

    items: list[T]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class PageParams:
    limit: int = DEFAULT_PAGE_SIZE
    offset: int = 0

    @property
    def window(self) -> Window:
        return Window(self.limit, self.offset)

    def page[T](self, items: list[T], total: int) -> Page[T]:
        return Page[T](items=items, total=total, limit=self.limit, offset=self.offset)


def page_params(
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PageParams:
    return PageParams(limit=limit, offset=offset)


def search_param(
    q: Annotated[str | None, Query(max_length=SEARCH_MAX, description="Подстрока без учёта регистра")] = None,
) -> str | None:
    """Поиск без пробелов по краям; пустая строка значит «без поиска»."""
    return search_text(q)


def sort_param(*, allowed: Sequence[str], default: str) -> Callable[..., SortKey]:
    """Зависимость `sort`: `field` или `-field` из `allowed`, иначе 422. Вторичный ключ id добавляет хранилище."""
    if SortKey.parse(default).field not in allowed:
        raise ValueError(f"сортировка по умолчанию {default!r} не входит в {list(allowed)}")
    pattern = rf"^-?(?:{'|'.join(re.escape(field) for field in allowed)})$"
    hint = f"Одно из: {', '.join(allowed)}; `-` в начале значит по убыванию"

    def dependency(sort: Annotated[str, Query(pattern=pattern, description=hint)] = default) -> SortKey:
        return SortKey.parse(sort)

    return dependency


@dataclass(frozen=True)
class PickerParams:
    q: str | None
    limit: int


def picker_params(
    q: Annotated[str | None, Query(max_length=SEARCH_MAX)] = None,
    limit: Annotated[int, Query(ge=1, le=PICKER_LIMIT)] = PICKER_LIMIT,
) -> PickerParams:
    """Пикер не листается: первые `limit` подходящих и признак `has_more` («уточните поиск»)."""
    return PickerParams(q=search_text(q), limit=limit)


PickerKind = Literal["user", "org", "group", "project", "runner"]


class PickerItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: PickerKind
    id: str
    name: str
    # Вторая строка подписи: почта человека, адрес организации.
    detail: str | None


class PickerList(BaseModel):
    """Ответ пикера: первые подходящие; `has_more` значит «уточните поиск», листать пикер нельзя."""

    model_config = ConfigDict(extra="forbid")

    items: list[PickerItem]
    has_more: bool
