"""Общие формы админ-API: страница списка, её параметры, порядок, поиск, курсор журналов и ответ пикера."""

from __future__ import annotations

import base64
import binascii
import inspect
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Annotated

from fastapi import Query
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict

from hse_doc_studio.core.listing import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    PICKER_LIMIT,
    PickerResult,
    SortOrder,
    Window,
)

MAX_PAGE_SIZE = MAX_PAGE_LIMIT
DEFAULT_PAGE_SIZE = DEFAULT_PAGE_LIMIT
MAX_QUERY_LENGTH = 200
# Курсор журнала: base64url от ключа последней строки; старые клиенты присылают сам ключ цифрами.
_LEGACY_CURSOR = re.compile(r"^[0-9]{1,18}$")
_CURSOR = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


class Page[T](BaseModel):
    """Страница списка: срез `items` и общее число записей `total` под тем же фильтром."""

    model_config = ConfigDict(extra="forbid")

    items: list[T]
    total: int
    limit: int
    offset: int


class PickerOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    id: str
    name: str
    detail: str | None


class PickerPage(BaseModel):
    """Первые совпадения пикера; при `has_more` интерфейс просит уточнить поиск."""

    model_config = ConfigDict(extra="forbid")

    items: list[PickerOption]
    has_more: bool


def picker_page(result: PickerResult) -> PickerPage:
    return PickerPage(
        items=[PickerOption(kind=i.kind, id=i.id, name=i.name, detail=i.detail) for i in result.items],
        has_more=result.has_more,
    )


@dataclass(frozen=True)
class PageParams:
    limit: int = DEFAULT_PAGE_SIZE
    offset: int = 0

    def page[T](self, items: list[T], total: int) -> Page[T]:
        return Page[T](items=items, total=total, limit=self.limit, offset=self.offset)

    @property
    def window(self) -> Window:
        return Window(limit=self.limit, offset=self.offset)


def page_params(
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PageParams:
    return PageParams(limit=limit, offset=offset)


def search_param(q: Annotated[str, Query(max_length=MAX_QUERY_LENGTH)] = "") -> str | None:
    """Подстрока поиска без пробелов по краям; пустая строка значит «без поиска»."""
    return q.strip() or None


def picker_limit(limit: Annotated[int, Query(ge=1, le=PICKER_LIMIT)] = PICKER_LIMIT) -> int:
    return limit


def sort_param(*, allowed: Sequence[str], default: str) -> Callable[..., SortOrder]:
    """Зависимость `sort=field|-field`: поле вне `allowed` даёт 422 ещё до обработчика."""
    fields = tuple(allowed)
    if default.removeprefix("-") not in fields:
        raise ValueError(f"порядок по умолчанию {default!r} вне разрешённых полей {fields}")
    pattern = "^-?(" + "|".join(re.escape(f) for f in fields) + ")$"
    description = "Поле порядка, `-` в начале значит по убыванию: " + ", ".join(fields)

    def dependency(sort: str = default) -> SortOrder:
        return SortOrder(field=sort.removeprefix("-"), descending=sort.startswith("-"))

    # Ограничения параметра своя у каждого ресурса; строковая аннотация (`from __future__`) не увидела бы
    # локальный `pattern`, поэтому сигнатура для FastAPI собирается явно.
    query = Annotated[str, Query(pattern=pattern, max_length=64, description=description)]
    parameter = inspect.Parameter("sort", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=default, annotation=query)
    dependency.__signature__ = inspect.Signature([parameter], return_annotation=SortOrder)  # type: ignore[attr-defined]
    return dependency


def encode_cursor(key: int) -> str:
    return base64.urlsafe_b64encode(str(key).encode("ascii")).rstrip(b"=").decode("ascii")


def _bad_cursor() -> RequestValidationError:
    return RequestValidationError([{"type": "value_error", "loc": ("query", "cursor"), "msg": "Invalid cursor"}])


def decode_cursor(raw: str | None) -> int | None:
    """Ключ из курсора; непонятный курсор даёт 422, а не первую страницу."""
    if not raw:
        return None
    if _LEGACY_CURSOR.match(raw):
        return int(raw)
    if not _CURSOR.match(raw):
        raise _bad_cursor()
    try:
        text = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("ascii")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise _bad_cursor() from exc
    if not _LEGACY_CURSOR.match(text):
        raise _bad_cursor()
    return int(text)


def cursor_param(cursor: Annotated[str | None, Query(max_length=32)] = None) -> int | None:
    return decode_cursor(cursor)
