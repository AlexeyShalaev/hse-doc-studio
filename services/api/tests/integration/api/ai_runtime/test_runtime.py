from __future__ import annotations

from httpx import AsyncClient

from tests.integration.api.ai_runtime.conftest import FakeOllamaRuntime


async def test__api__get_runtime_status__reports_not_running_by_default(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/ai-runtime/status")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["mode"] == "none"
    assert data["base_url"] is None
    assert data["installed_models"] == []


async def test__api__start_runtime__reflects_running_status(test_app: AsyncClient) -> None:
    resp = await test_app.post("/api/v1/ai-runtime/start")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["started"] is True
    assert data["status"]["mode"] == "docker"
    assert data["status"]["base_url"] == "http://127.0.0.1:11434"


async def test__api__start_runtime__then_status__stays_running(test_app: AsyncClient) -> None:
    await test_app.post("/api/v1/ai-runtime/start")

    resp = await test_app.get("/api/v1/ai-runtime/status")

    assert resp.status_code == 200, resp.text
    assert resp.json()["mode"] == "docker"


async def test__api__start_runtime__syncs_ollama_provider(
    test_app: AsyncClient, ollama_runtime: FakeOllamaRuntime
) -> None:
    ollama_runtime.installed_models = ["qwen2.5:0.5b"]

    await test_app.post("/api/v1/ai-runtime/start")

    providers = (await test_app.get("/api/v1/ai-providers")).json()
    [ollama_provider] = [p for p in providers if p["type"] == "ollama"]
    assert ollama_provider["models"] == ["qwen2.5:0.5b"]
    assert ollama_provider["base_url"] == "http://127.0.0.1:11434/v1"


async def test__api__stop_runtime__after_start__reports_stopped(test_app: AsyncClient) -> None:
    await test_app.post("/api/v1/ai-runtime/start")

    resp = await test_app.post("/api/v1/ai-runtime/stop")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["stopped"] is True
    assert data["status"]["mode"] == "none"
    assert data["status"]["base_url"] is None


async def test__api__stop_runtime__when_not_running__reports_not_stopped(test_app: AsyncClient) -> None:
    resp = await test_app.post("/api/v1/ai-runtime/stop")

    assert resp.status_code == 200, resp.text
    assert resp.json()["stopped"] is False
