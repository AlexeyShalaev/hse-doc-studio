"""Общие формы админ-API: страница списка и её параметры."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Query
from pydantic import BaseModel, ConfigDict

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50


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

    def page[T](self, items: list[T], total: int) -> Page[T]:
        return Page[T](items=items, total=total, limit=self.limit, offset=self.offset)


def page_params(
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PageParams:
    return PageParams(limit=limit, offset=offset)
