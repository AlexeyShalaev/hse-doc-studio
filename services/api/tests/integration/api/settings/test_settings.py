from __future__ import annotations

from httpx import AsyncClient


async def test__api__get_settings__returns_defaults(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/settings")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "theme" in data
    assert "compile_image" in data
    # LanguageTool is auto-managed now — no enable flag / URL in settings.
    assert "languagetool_enabled" not in data
    assert "languagetool_url" not in data


async def test__api__update_settings__theme_change_reflected(test_app: AsyncClient) -> None:
    resp = await test_app.put("/api/v1/settings", json={"theme": "light"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["theme"] == "light"


async def test__api__update_settings__partial_update_preserves_other_fields(test_app: AsyncClient) -> None:
    await test_app.put("/api/v1/settings", json={"theme": "light", "default_engine": "lualatex"})

    resp = await test_app.put("/api/v1/settings", json={"theme": "dark"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["theme"] == "dark"
    assert data["default_engine"] == "lualatex"


async def test__api__update_settings__empty_patch__returns_200(test_app: AsyncClient) -> None:
    resp = await test_app.put("/api/v1/settings", json={})
    assert resp.status_code == 200


async def test__api__get_settings__reflects_previous_update(test_app: AsyncClient) -> None:
    await test_app.put("/api/v1/settings", json={"theme": "light"})

    resp = await test_app.get("/api/v1/settings")
    assert resp.status_code == 200
    assert resp.json()["theme"] == "light"


async def test__api__get_settings__interface_language_defaults_to_ru(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/settings")

    assert resp.status_code == 200, resp.text
    assert resp.json()["interface_language"] == "ru"


async def test__api__update_settings__interface_language_round_trips(test_app: AsyncClient) -> None:
    resp = await test_app.put("/api/v1/settings", json={"interface_language": "en"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["interface_language"] == "en"

    # Independent from document language: changing it must not touch other fields.
    again = await test_app.get("/api/v1/settings")
    assert again.json()["interface_language"] == "en"


async def test__api__update_settings__interface_language_rejects_invalid(test_app: AsyncClient) -> None:
    resp = await test_app.put("/api/v1/settings", json={"interface_language": "de"})

    assert resp.status_code == 400, resp.text
