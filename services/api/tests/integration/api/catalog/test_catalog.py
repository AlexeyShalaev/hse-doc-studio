from __future__ import annotations

import pytest
from httpx import AsyncClient


async def test__api__catalog_list_packs__returns_nonempty_list(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/catalog/packs")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


async def test__api__catalog_list_packs__items_have_expected_fields(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/catalog/packs")

    assert resp.status_code == 200
    pack = resp.json()[0]
    assert "id" in pack
    assert "name" in pack
    assert "templates" in pack
    assert isinstance(pack["templates"], list)


async def test__api__catalog_list_versions__returns_list(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/catalog/packs/hse-cs-se/templates/vkr/versions")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


async def test__api__catalog_list_versions__items_have_version_field(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/catalog/packs/hse-cs-se/templates/vkr/versions")

    assert resp.status_code == 200
    item = resp.json()[0]
    assert "version" in item
    assert "status" in item
    assert "is_default" in item


async def test__api__catalog_list_versions__nonexistent_template__returns_404(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/catalog/packs/hse-cs-se/templates/no-such-template/versions")
    assert resp.status_code == 404


async def test__api__catalog_get_version__returns_detail(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/catalog/packs/hse-cs-se/templates/vkr/versions/2026.1")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "version" in data
    assert "documents" in data
    assert isinstance(data["documents"], list)
    assert "engine_config" in data


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/catalog/packs/hse-cs-se/templates/vkr/versions/9999.9",
        "/api/v1/catalog/packs/no-such-pack/templates/vkr/versions/2026.1",
    ],
    ids=["nonexistent-version", "nonexistent-pack"],
)
async def test__api__catalog_get_version__nonexistent__returns_404(test_app: AsyncClient, path: str) -> None:
    resp = await test_app.get(path)
    assert resp.status_code == 404
