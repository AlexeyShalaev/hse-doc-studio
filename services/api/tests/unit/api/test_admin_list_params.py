"""Общие параметры списков админки: окно, поиск, порядок из разрешённых полей и курсор журналов."""

from __future__ import annotations

import base64
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from hse_doc_studio.api.schemas.admin import (
    PageParams,
    cursor_param,
    decode_cursor,
    encode_cursor,
    page_params,
    picker_limit,
    search_param,
    sort_param,
)
from hse_doc_studio.core.listing import SortOrder

_SORT = sort_param(allowed=("name", "created_at"), default="-created_at")


def _client() -> TestClient:
    app = FastAPI()

    @app.get("/list")
    def listing(
        params: Annotated[PageParams, Depends(page_params)],
        q: Annotated[str | None, Depends(search_param)],
        sort: Annotated[SortOrder, Depends(_SORT)],
        cursor: Annotated[int | None, Depends(cursor_param)],
    ) -> dict[str, object]:
        return {
            "limit": params.limit,
            "offset": params.offset,
            "q": q,
            "sort": [sort.field, sort.descending],
            "cursor": cursor,
        }

    @app.get("/pick")
    def pick(limit: Annotated[int, Depends(picker_limit)]) -> int:
        return limit

    return TestClient(app)


def test__defaults() -> None:
    assert _client().get("/list").json() == {
        "limit": 50,
        "offset": 0,
        "q": None,
        "sort": ["created_at", True],
        "cursor": None,
    }


def test__picker_limit__default_20_max_20() -> None:
    client = _client()
    assert client.get("/pick").json() == 20
    assert client.get("/pick?limit=5").json() == 5
    assert client.get("/pick?limit=21").status_code == 422


@pytest.mark.parametrize(
    ("query", "key", "expected"),
    [
        ("sort=name", "sort", ["name", False]),
        ("sort=-name", "sort", ["name", True]),
        ("q=%20%20Анна%20", "q", "Анна"),
        ("q=%20%20%20", "q", None),
        ("q=", "q", None),
        ("limit=200&offset=10000", "limit", 200),
        ("cursor=", "cursor", None),
        ("cursor=1042", "cursor", 1042),
        ("cursor=MTA0Mg", "cursor", 1042),
    ],
)
def test__accepted(query: str, key: str, expected: object) -> None:
    response = _client().get(f"/list?{query}")
    assert response.status_code == 200
    assert response.json()[key] == expected


@pytest.mark.parametrize(
    "query",
    [
        "sort=email",
        "sort=--name",
        "sort=name-",
        "sort=Name",
        "sort=name,created_at",
        "limit=0",
        "limit=201",
        "offset=-1",
        "q=" + "x" * 201,
        "cursor=bad%20cursor",
        "cursor=" + base64.urlsafe_b64encode(b"-5").decode().rstrip("="),
        "cursor=" + "A" * 33,
    ],
)
def test__rejected_with_422(query: str) -> None:
    assert _client().get(f"/list?{query}").status_code == 422


def test__sort_param__default_outside_allowed__is_a_programming_error() -> None:
    with pytest.raises(ValueError, match="вне разрешённых"):
        sort_param(allowed=("name",), default="created_at")


@pytest.mark.parametrize("key", [0, 7, 1042, 10**17])
def test__cursor__roundtrip_is_opaque(key: int) -> None:
    encoded = encode_cursor(key)
    assert not encoded.isdigit()
    assert "=" not in encoded
    assert decode_cursor(encoded) == key


def test__cursor__not_base64__rejected() -> None:
    with pytest.raises(RequestValidationError):
        decode_cursor("!!")
