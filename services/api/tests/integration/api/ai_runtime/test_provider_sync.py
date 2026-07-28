from __future__ import annotations

from httpx import AsyncClient

from tests.integration.api.ai_runtime.conftest import FakeOllamaRuntime


async def test__api__sync_provider__runtime_not_running__creates_no_provider(test_app: AsyncClient) -> None:
    resp = await test_app.post("/api/v1/ai-runtime/provider/sync")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["provider_id"] is None
    assert data["models"] == []
    assert (await test_app.get("/api/v1/ai-providers")).json() == []


async def test__api__sync_provider__running_with_models__creates_real_provider_row(
    test_app: AsyncClient, ollama_runtime: FakeOllamaRuntime
) -> None:
    ollama_runtime.installed_models = ["qwen2.5:0.5b"]
    await test_app.post("/api/v1/ai-runtime/start")

    resp = await test_app.post("/api/v1/ai-runtime/provider/sync")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["provider_id"] is not None
    assert data["models"] == ["qwen2.5:0.5b"]

    # This part is real: the JSON-backed IAIProviderRepository actually persisted
    # the row, reachable through the (also real) ai-providers router.
    providers = (await test_app.get("/api/v1/ai-providers")).json()
    [provider] = [p for p in providers if p["type"] == "ollama"]
    assert provider["id"] == data["provider_id"]
    assert provider["name"] == "Ollama"  # settings.ollama.provider_name default
    assert provider["base_url"] == "http://127.0.0.1:11434/v1"
    assert provider["has_api_key"] is False


async def test__api__sync_provider__called_twice__upserts_single_row(
    test_app: AsyncClient, ollama_runtime: FakeOllamaRuntime
) -> None:
    ollama_runtime.installed_models = ["qwen2.5:0.5b"]
    await test_app.post("/api/v1/ai-runtime/start")
    first = (await test_app.post("/api/v1/ai-runtime/provider/sync")).json()

    ollama_runtime.installed_models = ["qwen2.5:0.5b", "llama3.2:1b"]
    second = (await test_app.post("/api/v1/ai-runtime/provider/sync")).json()

    assert second["provider_id"] == first["provider_id"]
    assert second["models"] == ["qwen2.5:0.5b", "llama3.2:1b"]
    providers = (await test_app.get("/api/v1/ai-providers")).json()
    assert len([p for p in providers if p["type"] == "ollama"]) == 1


async def test__api__stop_then_sync__leaves_existing_provider_record_untouched(
    test_app: AsyncClient, ollama_runtime: FakeOllamaRuntime
) -> None:
    ollama_runtime.installed_models = ["qwen2.5:0.5b"]
    await test_app.post("/api/v1/ai-runtime/start")
    started = (await test_app.post("/api/v1/ai-runtime/provider/sync")).json()

    await test_app.post("/api/v1/ai-runtime/stop")
    resp = await test_app.post("/api/v1/ai-runtime/provider/sync")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Runtime down: can't list models, so the known model list must not be wiped.
    assert data["provider_id"] == started["provider_id"]
    assert data["models"] == ["qwen2.5:0.5b"]
