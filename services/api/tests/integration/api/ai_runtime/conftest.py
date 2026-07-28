from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest_asyncio
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from hse_doc_studio.api.routers.v1 import api_router
from hse_doc_studio.core.entities import HardwareInfo, LoadedModel, OllamaRuntimeStatus, RegistryModel
from hse_doc_studio.core.enums import GpuVendor, OllamaRuntimeMode
from httpx import ASGITransport, AsyncClient

from tests.fixtures.app import create_test_container


class FakeHardwareProbe:
    """Deterministic stand-in for `SystemHardwareProbe` (real one shells out to
    nvidia-smi/psutil) — a plausible, fixed GPU/RAM/CPU reading so catalog
    recommendations are stable across test runs and hosts.
    """

    def __init__(self, hardware: HardwareInfo | None = None) -> None:
        self.hardware = hardware or HardwareInfo(
            gpu_vendor=GpuVendor.nvidia,
            gpu_name="NVIDIA GeForce RTX 4090",
            vram_mb=24576,
            total_ram_mb=65536,
            cpu_count=16,
            docker_gpu_supported=True,
        )

    async def detect(self) -> HardwareInfo:
        return self.hardware


class FakeOllamaRegistry:
    """Canned `ollama.com` search results — swapped in for `OllamaRegistryClient`
    (a best-effort HTML scrape) so registry search tests never hit the network.
    """

    def __init__(self, models: list[RegistryModel] | None = None) -> None:
        self.models = (
            models
            if models is not None
            else [
                RegistryModel(
                    name="qwen2.5",
                    description="Qwen2.5 instruct models from Alibaba.",
                    pulls="31.8M Pulls",
                    capabilities=["tools", "completion"],
                ),
                RegistryModel(
                    name="llama3.2",
                    description="Meta Llama 3.2 instruct models.",
                    pulls="12.4M Pulls",
                    capabilities=["completion"],
                ),
            ]
        )

    async def search(self, query: str) -> list[RegistryModel]:
        if not query:
            return list(self.models)
        needle = query.lower()
        return [m for m in self.models if needle in m.name.lower()]


class FakeOllamaRuntime:
    """In-memory stand-in for `OllamaRuntimeManager` — no Docker, no real Ollama
    HTTP API. Tests seed/mutate `installed_models` / `loaded_models` / `pull_lines`
    directly to drive scenarios; `IPullModelJobs` (the real `PullModelJobManager`)
    is wired against this fake via DI, so pull-job lifecycle tests exercise real
    background-task logic on top of this fake transport.
    """

    def __init__(
        self,
        *,
        docker_available: bool = True,
        engine_image_installed: bool = True,
        installed_models: list[str] | None = None,
        version: str = "0.4.0",
    ) -> None:
        self.running = False
        self.mode = OllamaRuntimeMode.none
        self.base_url: str | None = None
        self.version = version
        self.docker_available = docker_available
        self.engine_image_installed = engine_image_installed
        self.installed_models: list[str] = list(installed_models or [])
        self.loaded_models: list[LoadedModel] = []
        # Lines yielded by the next pull_model() call before the sentinel.
        self.pull_lines: list[str] = ["pulling: 50%", "pulling: 100%", "__DONE__"]
        self.stop_calls = 0
        self.ensure_running_calls = 0

    async def status(self) -> OllamaRuntimeStatus:
        return OllamaRuntimeStatus(
            mode=self.mode,
            base_url=self.base_url,
            version=self.version if self.running else None,
            docker_available=self.docker_available,
            engine_image_installed=self.engine_image_installed,
            installed_models=list(self.installed_models),
        )

    async def ensure_running(self) -> str | None:
        self.ensure_running_calls += 1
        self.running = True
        self.mode = OllamaRuntimeMode.docker
        self.base_url = "http://127.0.0.1:11434"
        return self.base_url

    async def list_installed_models(self) -> list[str]:
        return list(self.installed_models)

    async def list_loaded_models(self) -> list[LoadedModel]:
        return list(self.loaded_models)

    async def unload_model(self, name: str) -> bool:
        before = len(self.loaded_models)
        self.loaded_models = [m for m in self.loaded_models if m.name != name]
        return len(self.loaded_models) < before

    async def pull_model(self, name: str) -> AsyncGenerator[str, None]:
        lines = list(self.pull_lines)
        installed = self.installed_models

        async def _gen() -> AsyncGenerator[str, None]:
            for line in lines:
                # The real consumer (PullModelJobManager._run) stops iterating
                # the instant it sees "__DONE__" — any code placed *after* this
                # loop would never run, so the side effect has to land on the
                # same yield as the sentinel, not after it.
                if line == "__DONE__" and name not in installed:
                    installed.append(name)
                yield line

        return _gen()

    async def delete_model(self, name: str) -> bool:
        if name in self.installed_models:
            self.installed_models.remove(name)
            return True
        return False

    async def stop(self) -> tuple[bool, str | None]:
        self.stop_calls += 1
        was_running = self.running
        self.running = False
        self.mode = OllamaRuntimeMode.none
        self.base_url = None
        return was_running, None

    async def reconcile(self) -> OllamaRuntimeStatus:
        return await self.status()

    async def idle_reaper_loop(self) -> None:
        return None


@pytest_asyncio.fixture
async def hardware_probe() -> FakeHardwareProbe:
    return FakeHardwareProbe()


@pytest_asyncio.fixture
async def ollama_registry() -> FakeOllamaRegistry:
    return FakeOllamaRegistry()


@pytest_asyncio.fixture
async def ollama_runtime() -> FakeOllamaRuntime:
    return FakeOllamaRuntime()


@pytest_asyncio.fixture
async def test_app(
    tmp_path: Path,
    hardware_probe: FakeHardwareProbe,
    ollama_registry: FakeOllamaRegistry,
    ollama_runtime: FakeOllamaRuntime,
) -> AsyncClient:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    container = create_test_container(
        data_dir,
        hardware_probe=hardware_probe,
        ollama_registry=ollama_registry,
        ollama_runtime=ollama_runtime,
    )

    app = FastAPI()
    app.include_router(api_router)
    setup_dishka(container, app)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    await container.close()
