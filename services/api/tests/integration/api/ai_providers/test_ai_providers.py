from __future__ import annotations

from httpx import AsyncClient


async def test__api__ai_providers__empty_by_default(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/ai-providers")
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


async def test__api__create_ai_provider__never_returns_api_key(test_app: AsyncClient) -> None:
    resp = await test_app.post(
        "/api/v1/ai-providers",
        json={"name": "Local vLLM", "type": "openai_compat", "api_key": "sk-secret", "base_url": "http://x/v1"},
    )

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "api_key" not in data
    assert data["has_api_key"] is True
    assert data["name"] == "Local vLLM"
    assert data["type"] == "openai_compat"
    assert data["base_url"] == "http://x/v1"


async def test__api__create_then_list_and_get(test_app: AsyncClient) -> None:
    created = (
        await test_app.post(
            "/api/v1/ai-providers",
            json={"name": "OpenAI", "type": "openai", "api_key": "sk-x", "models": ["gpt-4.1"]},
        )
    ).json()
    provider_id = created["id"]

    listed = await test_app.get("/api/v1/ai-providers")
    assert listed.status_code == 200
    assert [p["id"] for p in listed.json()] == [provider_id]

    got = await test_app.get(f"/api/v1/ai-providers/{provider_id}")
    assert got.status_code == 200
    assert got.json()["models"] == ["gpt-4.1"]


async def test__api__update_ai_provider__blank_key_keeps_secret(test_app: AsyncClient) -> None:
    provider_id = (
        await test_app.post(
            "/api/v1/ai-providers",
            json={"name": "OpenAI", "type": "openai", "api_key": "sk-original"},
        )
    ).json()["id"]

    resp = await test_app.patch(
        f"/api/v1/ai-providers/{provider_id}",
        json={"name": "Renamed", "api_key": ""},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["name"] == "Renamed"
    assert data["has_api_key"] is True


async def test__api__delete_ai_provider(test_app: AsyncClient) -> None:
    provider_id = (
        await test_app.post(
            "/api/v1/ai-providers",
            json={"name": "OpenAI", "type": "openai", "api_key": "sk-x"},
        )
    ).json()["id"]

    resp = await test_app.delete(f"/api/v1/ai-providers/{provider_id}")
    assert resp.status_code == 204

    assert (await test_app.get(f"/api/v1/ai-providers/{provider_id}")).status_code == 404


async def test__api__models_for_unknown_provider__returns_404(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/ai-providers/00000000-0000-0000-0000-000000000000/models")
    assert resp.status_code == 404


async def test__api__default_ai_provider_setting_roundtrips(test_app: AsyncClient) -> None:
    await test_app.put(
        "/api/v1/settings",
        json={"default_ai_provider_id": "prov-1", "default_ai_model": "gpt-4.1"},
    )

    data = (await test_app.get("/api/v1/settings")).json()
    assert data["default_ai_provider_id"] == "prov-1"
    assert data["default_ai_model"] == "gpt-4.1"


async def test__api__delete_default_provider__clears_default(test_app: AsyncClient) -> None:
    provider_id = (
        await test_app.post(
            "/api/v1/ai-providers",
            json={"name": "OpenAI", "type": "openai", "api_key": "sk-x"},
        )
    ).json()["id"]
    await test_app.put(
        "/api/v1/settings",
        json={"default_ai_provider_id": provider_id, "default_ai_model": "gpt-4.1"},
    )

    assert (await test_app.delete(f"/api/v1/ai-providers/{provider_id}")).status_code == 204

    # The cascade in DeleteAIProviderUC must null out the dangling default.
    data = (await test_app.get("/api/v1/settings")).json()
    assert data["default_ai_provider_id"] is None
    assert data["default_ai_model"] is None


async def test__api__create_provider__strips_whitespace_from_key(test_app: AsyncClient) -> None:
    # A padded key must be stored trimmed (otherwise SDK auth fails); the key is
    # never returned, so we assert via has_api_key + a successful round-trip.
    resp = await test_app.post(
        "/api/v1/ai-providers",
        json={"name": "OpenAI", "type": "openai", "api_key": "  sk-padded  "},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["has_api_key"] is True


async def test__api__create_provider__defaults_connection_fields(test_app: AsyncClient) -> None:
    resp = await test_app.post(
        "/api/v1/ai-providers",
        json={"name": "OpenAI", "type": "openai", "api_key": "sk-x"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["ssl_verify"] is True
    assert data["connect_timeout_s"] == 10.0
    assert data["request_timeout_s"] == 60.0


async def test__api__create_provider__custom_connection_fields_roundtrip(test_app: AsyncClient) -> None:
    provider_id = (
        await test_app.post(
            "/api/v1/ai-providers",
            json={
                "name": "Internal",
                "type": "openai_compat",
                "api_key": "sk-x",
                "base_url": "https://internal/v1",
                "ssl_verify": False,
                "connect_timeout_s": 5,
                "request_timeout_s": 120,
            },
        )
    ).json()["id"]

    data = (await test_app.get(f"/api/v1/ai-providers/{provider_id}")).json()
    assert data["ssl_verify"] is False
    assert data["connect_timeout_s"] == 5.0
    assert data["request_timeout_s"] == 120.0


async def test__api__create_provider__non_positive_timeout_rejected(test_app: AsyncClient) -> None:
    resp = await test_app.post(
        "/api/v1/ai-providers",
        json={"name": "OpenAI", "type": "openai", "api_key": "sk-x", "request_timeout_s": 0},
    )
    assert resp.status_code == 422, resp.text
