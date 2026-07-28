from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Protocol

from hse_doc_studio.core.entities import (
    HardwareInfo,
    LoadedModel,
    OllamaRuntimeStatus,
    PullJob,
    RegistryModel,
)


class IHardwareProbe(Protocol):
    # Best-effort detection of the host's GPU/RAM/CPU. Implemented in infra
    # (shells out to nvidia-smi / system tools); defined here so use cases can
    # depend on it without importing infra. MUST never raise — unknown fields
    # come back as None / GpuVendor.none.
    async def detect(self) -> HardwareInfo: ...


class IPullModelJobs(Protocol):
    # Manages background model-download jobs that run independently of the
    # request that started them (so the UI can close/reconnect freely).
    # Implemented in infra.
    async def start(self, name: str) -> PullJob: ...

    def list_jobs(self) -> list[PullJob]: ...

    def dismiss(self, name: str) -> None: ...


class IOllamaRegistry(Protocol):
    # Searches the public Ollama model registry (ollama.com) for discovery.
    # Implemented in infra (best-effort HTML scrape); MUST return [] on any
    # error rather than raise, like the Docker Hub tag listing.
    async def search(self, query: str) -> list[RegistryModel]: ...


class IOllamaRuntime(Protocol):
    # Orchestrates a local Ollama runtime (a user-run native binary if present,
    # otherwise our managed `ollama/ollama` Docker container) and speaks to it
    # over its HTTP API. Implemented in infra; the use-case/API layer depends
    # only on this protocol. Model dispatch reaches Ollama through the existing
    # OpenAI-compatible client — this protocol only covers lifecycle + the
    # native pull/list/delete management API.
    async def status(self) -> OllamaRuntimeStatus: ...

    async def ensure_running(self) -> str | None:
        # Make the runtime reachable (start/adopt the container if there is no
        # native server) and return its base URL, or None if unavailable.
        ...

    async def list_installed_models(self) -> list[str]: ...

    async def list_loaded_models(self) -> list[LoadedModel]:
        # Models currently held in memory (Ollama /api/ps).
        ...

    async def unload_model(self, name: str) -> bool:
        # Free a model from memory now (keep_alive=0), without waiting for the
        # idle window. Returns False if the runtime is unreachable.
        ...

    async def pull_model(self, name: str) -> AsyncGenerator[str, None]:
        # Stream human-readable progress lines for `ollama pull <name>`, ending
        # with the sentinel "__DONE__" on success or "__FAILED__" on error
        # (mirrors the LanguageTool image-install stream).
        ...

    async def delete_model(self, name: str) -> bool: ...

    async def stop(self) -> tuple[bool, str | None]:
        # Stop the managed container (no-op for a native runtime we don't own).
        ...

    async def reconcile(self) -> OllamaRuntimeStatus:
        # Startup hook: adopt an already-running managed container.
        ...

    async def idle_reaper_loop(self) -> None:
        # Background loop: stop the managed container after the idle timeout.
        ...
