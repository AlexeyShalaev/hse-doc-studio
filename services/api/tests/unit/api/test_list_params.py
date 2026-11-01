"""Общие параметры серверных списков: сортировка из разрешённых полей, поиск, окно, пикер и курсор журнала."""

from __future__ import annotations

from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from hse_doc_studio.api.schemas.admin import (
    PageParams,
    PickerParams,
    decode_cursor,
    encode_cursor,
    page_params,
    picker_params,
    search_param,
    sort_param,
)
from hse_doc_studio.core.listing import Picked, SortKey, like_escaped, search_text

_sort = sort_param(allowed=("name", "created_at"), default="-created_at")


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()

    @app.get("/list")
    async def listing(
        params: Annotated[PageParams, Depends(page_params)],
        q: Annotated[str | None, Depends(search_param)],
        sort: Annotated[SortKey, Depends(_sort)],
    ) -> dict[str, object]:
        return {"limit": params.limit, "offset": params.offset, "q": q, "sort": str(sort)}

    @app.get("/pick")
    async def pick(params: Annotated[PickerParams, Depends(picker_params)]) -> dict[str, object]:
        return {"q": params.q, "limit": params.limit}

    return TestClient(app)


def test__list_params__defaults(client: TestClient) -> None:
    assert client.get("/list").json() == {"limit": 50, "offset": 0, "q": None, "sort": "-created_at"}


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("sort=name", "name"),
        ("sort=-name", "-name"),
        ("sort=created_at", "created_at"),
    ],
)
def test__sort__allowed_fields_in_both_directions(client: TestClient, query: str, expected: str) -> None:
    assert client.get(f"/list?{query}").json()["sort"] == expected


@pytest.mark.parametrize(
    "query",
    ["sort=email", "sort=--name", "sort=name,email", "sort=", "limit=0", "limit=201", "offset=-1", "q=" + "x" * 201],
)
def test__list_params__invalid__422(client: TestClient, query: str) -> None:
    assert client.get(f"/list?{query}").status_code == 422


def test__search__trimmed_and_blank_means_none(client: TestClient) -> None:
    assert client.get("/list", params={"q": "  Анна  "}).json()["q"] == "Анна"
    assert client.get("/list", params={"q": "   "}).json()["q"] is None


def test__picker__limit_capped_at_twenty(client: TestClient) -> None:
    assert client.get("/pick").json() == {"q": None, "limit": 20}
    assert client.get("/pick?limit=21").status_code == 422
    assert client.get("/pick?limit=0").status_code == 422


def test__sort_param__default_outside_allowed__refused_at_startup() -> None:
    with pytest.raises(ValueError, match="email"):
        sort_param(allowed=("name",), default="email")


def test__cursor__roundtrip_is_opaque_and_legacy_digits_still_accepted() -> None:
    cursor = encode_cursor(4181)

    assert not cursor.isdigit()
    assert "=" not in cursor
    assert decode_cursor(cursor) == 4181
    assert decode_cursor("4181") == 4181


@pytest.mark.parametrize("raw", ["abc", "-1", "a2V5OjE", encode_cursor(1) + "x", "=="])
def test__cursor__garbage__value_error(raw: str) -> None:
    with pytest.raises(ValueError, match="cursor"):
        decode_cursor(raw)


def test__core_helpers__search_text_like_and_picked() -> None:
    assert search_text(None) is None
    assert search_text(" a ") == "a"
    assert like_escaped("50%_a\\b") == "%50\\%\\_a\\\\b%"
    assert Picked.of([1, 2, 3], 2) == Picked([1, 2], has_more=True)
    assert Picked.of([1, 2], 2) == Picked([1, 2], has_more=False)
    assert SortKey.parse("-name") == SortKey("name", descending=True)
