from __future__ import annotations

import pytest
from hse_doc_studio.core.entities import LoadedModel
from httpx import AsyncClient

from tests.integration.api.ai_runtime.conftest import FakeOllamaRuntime


async def test__api__list_loaded_models__empty_by_default(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/ai-runtime/models/loaded")

    assert resp.status_code == 200, resp.text
    assert resp.json()["models"] == []


async def test__api__list_loaded_models__reflects_runtime_state(
    test_app: AsyncClient, ollama_runtime: FakeOllamaRuntime
) -> None:
    ollama_runtime.loaded_models = [
        LoadedModel(
            name="qwen2.5:0.5b", size_bytes=512_000_000, vram_bytes=512_000_000, expires_at="2026-07-21T12:00:00Z"
        )
    ]

    resp = await test_app.get("/api/v1/ai-runtime/models/loaded")

    assert resp.status_code == 200, resp.text
    [model] = resp.json()["models"]
    assert model["name"] == "qwen2.5:0.5b"
    assert model["size_bytes"] == 512_000_000
    assert model["vram_bytes"] == 512_000_000
    assert model["expires_at"] == "2026-07-21T12:00:00Z"


async def test__api__unload_model__loaded_model__frees_it(
    test_app: AsyncClient, ollama_runtime: FakeOllamaRuntime
) -> None:
    ollama_runtime.loaded_models = [LoadedModel(name="qwen2.5:0.5b", size_bytes=1, vram_bytes=1, expires_at=None)]

    resp = await test_app.post("/api/v1/ai-runtime/models/unload", params={"name": "qwen2.5:0.5b"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["unloaded"] is True
    assert (await test_app.get("/api/v1/ai-runtime/models/loaded")).json()["models"] == []


async def test__api__unload_model__not_loaded__returns_false(test_app: AsyncClient) -> None:
    resp = await test_app.post("/api/v1/ai-runtime/models/unload", params={"name": "qwen2.5:0.5b"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["unloaded"] is False


@pytest.mark.parametrize("name", ["  ", "!! bad !!"], ids=["blank", "invalid-format"])
async def test__api__unload_model__invalid_name__returns_400(test_app: AsyncClient, name: str) -> None:
    resp = await test_app.post("/api/v1/ai-runtime/models/unload", params={"name": name})

    assert resp.status_code == 400, resp.text
