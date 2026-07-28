from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.integration.api.ai_runtime.conftest import FakeOllamaRuntime


async def test__api__delete_model__installed_model__removes_it(
    test_app: AsyncClient, ollama_runtime: FakeOllamaRuntime
) -> None:
    ollama_runtime.installed_models = ["qwen2.5:0.5b"]

    resp = await test_app.delete("/api/v1/ai-runtime/models", params={"name": "qwen2.5:0.5b"})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["deleted"] is True
    assert data["installed_models"] == []


async def test__api__delete_model__not_installed__returns_false(test_app: AsyncClient) -> None:
    resp = await test_app.delete("/api/v1/ai-runtime/models", params={"name": "qwen2.5:0.5b"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] is False


async def test__api__delete_model__syncs_remaining_models_into_response(
    test_app: AsyncClient, ollama_runtime: FakeOllamaRuntime
) -> None:
    ollama_runtime.installed_models = ["qwen2.5:0.5b", "llama3.2:1b"]
    # The provider sync step only reflects live installed_models while the
    # runtime is reachable (base_url set) — see SyncLocalOllamaProviderUC.
    await test_app.post("/api/v1/ai-runtime/start")

    resp = await test_app.delete("/api/v1/ai-runtime/models", params={"name": "qwen2.5:0.5b"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["installed_models"] == ["llama3.2:1b"]


@pytest.mark.parametrize("name", [" ", "!! bad !!"], ids=["blank", "invalid-format"])
async def test__api__delete_model__invalid_name__returns_400(test_app: AsyncClient, name: str) -> None:
    resp = await test_app.delete("/api/v1/ai-runtime/models", params={"name": name})

    assert resp.status_code == 400, resp.text
