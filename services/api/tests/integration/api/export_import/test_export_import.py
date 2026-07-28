from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from hse_doc_studio.api.routers.v1 import api_router
from httpx import ASGITransport, AsyncClient

from tests.fixtures.app import create_test_container

# A minimal, always-valid ImportRequest envelope: `version`/`exported_at` are
# required by the shared ExportBundle schema but unused by the use case itself.
_ENVELOPE = {"version": "1.0", "exported_at": "2026-01-01T00:00:00Z"}


@asynccontextmanager
async def _fresh_client(data_dir: Path) -> AsyncIterator[AsyncClient]:
    """A second, independent app instance backed by its own empty data_dir.

    Used to prove an export bundle actually round-trips into a clean state,
    rather than merely surviving a no-op re-import into the same store.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    container = create_test_container(data_dir)
    app = FastAPI()
    app.include_router(api_router)
    setup_dishka(container, app)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    await container.close()


async def test__api__export_data__defaults__returns_unencrypted_bundle_with_current_settings(
    test_app: AsyncClient,
) -> None:
    resp = await test_app.post("/api/v1/data/export", json={})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["encrypted"] is False
    assert body["settings"]["theme"] == "system"
    assert body["ai_providers"] == []
    assert body["agent_personas"] == []


async def test__api__export_data__include_settings_false__omits_settings(test_app: AsyncClient) -> None:
    resp = await test_app.post("/api/v1/data/export", json={"include_settings": False})

    assert resp.status_code == 200, resp.text
    assert resp.json()["settings"] is None


async def test__api__export_data__password_without_provider_keys__not_marked_encrypted(
    test_app: AsyncClient,
) -> None:
    # A password with nothing to encrypt must not flip `encrypted` — otherwise
    # import would accept ANY password since there's nothing to verify it against.
    resp = await test_app.post("/api/v1/data/export", json={"encryption_password": "pw123"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["encrypted"] is False


async def test__api__export_data__with_provider_and_password__encrypts_api_key_and_marks_encrypted(
    test_app: AsyncClient,
) -> None:
    await test_app.post(
        "/api/v1/ai-providers",
        json={"name": "OpenAI", "type": "openai", "api_key": "sk-secret"},
    )

    resp = await test_app.post("/api/v1/data/export", json={"encryption_password": "pw123"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["encrypted"] is True
    record = body["ai_providers"][0]
    assert record["api_key"] != "sk-secret"
    assert ":" in record["api_key"]  # salt:ciphertext shape from encrypt_token


async def test__api__export_then_import__roundtrips_settings_provider_and_persona_into_fresh_state(
    test_app: AsyncClient, tmp_path_factory: pytest.TempPathFactory
) -> None:
    await test_app.put("/api/v1/settings", json={"theme": "light"})
    await test_app.post(
        "/api/v1/ai-providers",
        json={"name": "OpenAI", "type": "openai", "api_key": "sk-x"},
    )
    await test_app.post(
        "/api/v1/agent-personas",
        json={"label": "Reviewer", "instruction": "Be strict"},
    )

    bundle = (await test_app.post("/api/v1/data/export", json={})).json()

    async with _fresh_client(tmp_path_factory.mktemp("export-import-fresh") / "data") as fresh:
        resp = await fresh.post("/api/v1/data/import", json={**bundle, "merge_strategy": "skip"})

        assert resp.status_code == 201, resp.text
        result = resp.json()
        assert result["settings_imported"] is True
        assert result["ai_providers_imported"] == 1
        assert result["ai_providers_skipped"] == 0
        assert result["agent_personas_imported"] == 1
        assert result["agent_personas_skipped"] == 0
        assert result["errors"] == []

        settings = (await fresh.get("/api/v1/settings")).json()
        assert settings["theme"] == "light"

        providers = (await fresh.get("/api/v1/ai-providers")).json()
        assert providers[0]["name"] == "OpenAI"

        personas = (await fresh.get("/api/v1/agent-personas")).json()
        assert personas[0]["label"] == "Reviewer"


async def test__api__import_data__merge_strategy_skip__existing_provider_by_id_is_skipped(
    test_app: AsyncClient,
) -> None:
    await test_app.post(
        "/api/v1/ai-providers",
        json={"name": "Original", "type": "openai", "api_key": "sk-x"},
    )
    bundle = (await test_app.post("/api/v1/data/export", json={})).json()

    resp = await test_app.post("/api/v1/data/import", json={**bundle, "merge_strategy": "skip"})

    assert resp.status_code == 201, resp.text
    result = resp.json()
    assert result["ai_providers_skipped"] == 1
    assert result["ai_providers_imported"] == 0

    providers = (await test_app.get("/api/v1/ai-providers")).json()
    assert len(providers) == 1
    assert providers[0]["name"] == "Original"


async def test__api__import_data__merge_strategy_replace__existing_provider_is_overwritten(
    test_app: AsyncClient,
) -> None:
    await test_app.post(
        "/api/v1/ai-providers",
        json={"name": "Original", "type": "openai", "api_key": "sk-x"},
    )
    bundle = (await test_app.post("/api/v1/data/export", json={})).json()
    bundle["ai_providers"][0]["name"] = "Updated"

    resp = await test_app.post("/api/v1/data/import", json={**bundle, "merge_strategy": "replace"})

    assert resp.status_code == 201, resp.text
    result = resp.json()
    assert result["ai_providers_imported"] == 1
    assert result["ai_providers_skipped"] == 0

    providers = (await test_app.get("/api/v1/ai-providers")).json()
    assert len(providers) == 1  # overwritten in place, not duplicated
    assert providers[0]["name"] == "Updated"


async def test__api__import_data__persona_merge_strategy_skip__existing_persona_is_kept(
    test_app: AsyncClient,
) -> None:
    await test_app.post(
        "/api/v1/agent-personas",
        json={"label": "Reviewer", "instruction": "Be strict"},
    )
    bundle = (await test_app.post("/api/v1/data/export", json={})).json()

    resp = await test_app.post("/api/v1/data/import", json={**bundle, "merge_strategy": "skip"})

    assert resp.status_code == 201, resp.text
    result = resp.json()
    assert result["agent_personas_skipped"] == 1
    assert result["agent_personas_imported"] == 0


async def test__api__import_data__unknown_merge_strategy__falls_back_to_skip(test_app: AsyncClient) -> None:
    await test_app.post(
        "/api/v1/ai-providers",
        json={"name": "Original", "type": "openai", "api_key": "sk-x"},
    )
    bundle = (await test_app.post("/api/v1/data/export", json={})).json()

    resp = await test_app.post("/api/v1/data/import", json={**bundle, "merge_strategy": "bogus"})

    assert resp.status_code == 201, resp.text
    assert resp.json()["ai_providers_skipped"] == 1


async def test__api__import_data__encrypted_without_password__returns_400(test_app: AsyncClient) -> None:
    resp = await test_app.post(
        "/api/v1/data/import",
        json={**_ENVELOPE, "encrypted": True, "ai_providers": [], "agent_personas": []},
    )

    assert resp.status_code == 400, resp.text
    assert "пароль" in resp.json()["detail"].lower()


async def test__api__export_then_import_encrypted__wrong_password__returns_400_and_writes_nothing(
    test_app: AsyncClient,
) -> None:
    await test_app.post(
        "/api/v1/ai-providers",
        json={"name": "OpenAI", "type": "openai", "api_key": "sk-secret"},
    )
    bundle = (await test_app.post("/api/v1/data/export", json={"encryption_password": "correct-pw"})).json()

    resp = await test_app.post(
        "/api/v1/data/import",
        json={**bundle, "merge_strategy": "replace", "decryption_password": "wrong-pw"},
    )

    assert resp.status_code == 400, resp.text
    assert "пароль" in resp.json()["detail"].lower()

    # Verified up front, before any write: no duplicate/overwritten records.
    providers = (await test_app.get("/api/v1/ai-providers")).json()
    assert len(providers) == 1
    assert providers[0]["name"] == "OpenAI"


async def test__api__export_then_import_encrypted__correct_password__decrypts_into_fresh_state(
    test_app: AsyncClient, tmp_path_factory: pytest.TempPathFactory
) -> None:
    await test_app.post(
        "/api/v1/ai-providers",
        json={"name": "OpenAI", "type": "openai", "api_key": "sk-secret"},
    )
    bundle = (await test_app.post("/api/v1/data/export", json={"encryption_password": "pw123"})).json()
    assert bundle["encrypted"] is True

    async with _fresh_client(tmp_path_factory.mktemp("export-import-encrypted") / "data") as fresh:
        resp = await fresh.post(
            "/api/v1/data/import",
            json={**bundle, "decryption_password": "pw123"},
        )

        assert resp.status_code == 201, resp.text
        result = resp.json()
        assert result["ai_providers_imported"] == 1
        assert result["errors"] == []

        providers = (await fresh.get("/api/v1/ai-providers")).json()
        assert providers[0]["has_api_key"] is True
