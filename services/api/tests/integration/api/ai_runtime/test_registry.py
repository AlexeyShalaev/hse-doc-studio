from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.parametrize(
    ("query", "expected_names"),
    [("qwen", ["qwen2.5"]), ("nonexistent-model-xyz", [])],
    ids=["match", "no-match"],
)
async def test__api__search_registry__query__returns_matching_names(
    test_app: AsyncClient, query: str, expected_names: list[str]
) -> None:
    resp = await test_app.get("/api/v1/ai-runtime/registry/search", params={"q": query})

    assert resp.status_code == 200, resp.text
    assert [m["name"] for m in resp.json()["models"]] == expected_names


async def test__api__search_registry__match__includes_pulls_and_capabilities(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/ai-runtime/registry/search", params={"q": "qwen"})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["models"][0]["pulls"] == "31.8M Pulls"
    assert data["models"][0]["capabilities"] == ["tools", "completion"]


async def test__api__search_registry__missing_query__returns_422(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/ai-runtime/registry/search")

    assert resp.status_code == 422
