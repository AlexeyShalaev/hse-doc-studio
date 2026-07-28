from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient

from tests.integration.api.ai_runtime.conftest import FakeOllamaRuntime


async def _wait_for_job(test_app: AsyncClient, name: str, *, attempts: int = 200) -> dict:
    for _ in range(attempts):
        jobs = (await test_app.get("/api/v1/ai-runtime/models/pulls")).json()["jobs"]
        job = next((j for j in jobs if j["name"] == name), None)
        if job is not None and job["state"] != "running":
            return job
        await asyncio.sleep(0.005)
    raise AssertionError(f"pull job {name!r} did not finish in time")


def _block_pull(runtime: FakeOllamaRuntime, release: asyncio.Event) -> None:
    async def _pull_model(name: str) -> AsyncGenerator[str, None]:
        async def _gen() -> AsyncGenerator[str, None]:
            await release.wait()
            yield "__DONE__"

        return _gen()

    runtime.pull_model = _pull_model  # type: ignore[method-assign]


async def test__api__start_pull__catalog_model__returns_running_job(test_app: AsyncClient) -> None:
    resp = await test_app.post("/api/v1/ai-runtime/models/pull", params={"name": "qwen2.5:0.5b"})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["name"] == "qwen2.5:0.5b"
    assert data["state"] == "running"
    assert data["error"] is None


async def test__api__start_pull__then_list_pulls__job_appears(test_app: AsyncClient) -> None:
    await test_app.post("/api/v1/ai-runtime/models/pull", params={"name": "qwen2.5:0.5b"})

    resp = await test_app.get("/api/v1/ai-runtime/models/pulls")

    assert resp.status_code == 200, resp.text
    assert [j["name"] for j in resp.json()["jobs"]] == ["qwen2.5:0.5b"]


async def test__api__start_pull__completes__job_becomes_success(test_app: AsyncClient) -> None:
    await test_app.post("/api/v1/ai-runtime/models/pull", params={"name": "qwen2.5:0.5b"})

    job = await _wait_for_job(test_app, "qwen2.5:0.5b")

    assert job["state"] == "success"
    assert job["error"] is None


async def test__api__start_pull__completes__installs_the_model(
    test_app: AsyncClient, ollama_runtime: FakeOllamaRuntime
) -> None:
    await test_app.post("/api/v1/ai-runtime/models/pull", params={"name": "qwen2.5:0.5b"})

    await _wait_for_job(test_app, "qwen2.5:0.5b")

    assert "qwen2.5:0.5b" in ollama_runtime.installed_models


async def test__api__start_pull__failing_stream__job_becomes_failure_with_error(
    test_app: AsyncClient, ollama_runtime: FakeOllamaRuntime
) -> None:
    ollama_runtime.pull_lines = ["pulling: 10%", "Ошибка: model not found", "__FAILED__"]

    await test_app.post("/api/v1/ai-runtime/models/pull", params={"name": "qwen2.5:0.5b"})
    job = await _wait_for_job(test_app, "qwen2.5:0.5b")

    assert job["state"] == "failure"
    assert job["error"] == "Ошибка: model not found"


@pytest.mark.parametrize("name", ["!! not a model !!", "   "], ids=["invalid-format", "blank"])
async def test__api__start_pull__invalid_name__returns_400(test_app: AsyncClient, name: str) -> None:
    resp = await test_app.post("/api/v1/ai-runtime/models/pull", params={"name": name})

    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]


async def test__api__dismiss_pull__removes_finished_job(test_app: AsyncClient) -> None:
    await test_app.post("/api/v1/ai-runtime/models/pull", params={"name": "qwen2.5:0.5b"})
    await _wait_for_job(test_app, "qwen2.5:0.5b")

    resp = await test_app.delete("/api/v1/ai-runtime/models/pulls", params={"name": "qwen2.5:0.5b"})

    assert resp.status_code == 204, resp.text
    assert (await test_app.get("/api/v1/ai-runtime/models/pulls")).json()["jobs"] == []


async def test__api__dismiss_pull__running_job_is_kept(
    test_app: AsyncClient, ollama_runtime: FakeOllamaRuntime
) -> None:
    release = asyncio.Event()
    _block_pull(ollama_runtime, release)
    await test_app.post("/api/v1/ai-runtime/models/pull", params={"name": "qwen2.5:0.5b"})

    await test_app.delete("/api/v1/ai-runtime/models/pulls", params={"name": "qwen2.5:0.5b"})

    jobs = (await test_app.get("/api/v1/ai-runtime/models/pulls")).json()["jobs"]
    assert [j["name"] for j in jobs] == ["qwen2.5:0.5b"]
    assert jobs[0]["state"] == "running"

    release.set()
    await _wait_for_job(test_app, "qwen2.5:0.5b")


async def test__api__start_pull__same_name_while_running__is_idempotent(
    test_app: AsyncClient, ollama_runtime: FakeOllamaRuntime
) -> None:
    release = asyncio.Event()
    _block_pull(ollama_runtime, release)
    first = (await test_app.post("/api/v1/ai-runtime/models/pull", params={"name": "qwen2.5:0.5b"})).json()

    second = (await test_app.post("/api/v1/ai-runtime/models/pull", params={"name": "qwen2.5:0.5b"})).json()

    assert second == first
    jobs = (await test_app.get("/api/v1/ai-runtime/models/pulls")).json()["jobs"]
    assert len(jobs) == 1  # one job per model, not duplicated

    release.set()
    await _wait_for_job(test_app, "qwen2.5:0.5b")


async def test__api__start_pull__over_concurrency_cap__returns_400(
    test_app: AsyncClient, ollama_runtime: FakeOllamaRuntime
) -> None:
    release = asyncio.Event()
    _block_pull(ollama_runtime, release)
    # settings.ollama.max_concurrent_pulls defaults to 2.
    await test_app.post("/api/v1/ai-runtime/models/pull", params={"name": "qwen2.5:0.5b"})
    await test_app.post("/api/v1/ai-runtime/models/pull", params={"name": "llama3.2:1b"})

    resp = await test_app.post("/api/v1/ai-runtime/models/pull", params={"name": "qwen2.5:1.5b"})

    assert resp.status_code == 400, resp.text

    release.set()
    await _wait_for_job(test_app, "qwen2.5:0.5b")
    await _wait_for_job(test_app, "llama3.2:1b")
