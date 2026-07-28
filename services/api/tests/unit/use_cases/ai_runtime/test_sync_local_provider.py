from __future__ import annotations

from uuid import UUID

import pytest
from hse_doc_studio.core.entities import AIProvider, OllamaRuntimeStatus
from hse_doc_studio.core.enums import AIProviderType, OllamaRuntimeMode
from hse_doc_studio.use_cases.ai_runtime.sync_local_provider import SyncLocalOllamaProviderUC


class _FakeRuntime:
    def __init__(self, status: OllamaRuntimeStatus) -> None:
        self._status = status

    async def status(self) -> OllamaRuntimeStatus:
        return self._status


class _FakeProviderRepo:
    def __init__(self) -> None:
        self.items: list[AIProvider] = []

    def list_all(self) -> list[AIProvider]:
        return list(self.items)

    def get(self, provider_id: UUID) -> AIProvider | None:
        return next((p for p in self.items if p.id == provider_id), None)

    def create(self, provider: AIProvider) -> None:
        self.items.append(provider)

    def update(self, provider: AIProvider) -> None:
        self.items = [provider if p.id == provider.id else p for p in self.items]

    def delete(self, provider_id: UUID) -> bool:
        before = len(self.items)
        self.items = [p for p in self.items if p.id != provider_id]
        return len(self.items) != before


def _status(mode: OllamaRuntimeMode, base_url: str | None, models: list[str]) -> OllamaRuntimeStatus:
    return OllamaRuntimeStatus(
        mode=mode,
        base_url=base_url,
        version="0.5.0" if base_url else None,
        docker_available=True,
        engine_image_installed=True,
        installed_models=models,
    )


@pytest.mark.unit
async def test__sync__creates_managed_provider_pointing_at_v1_endpoint() -> None:
    repo = _FakeProviderRepo()
    runtime = _FakeRuntime(_status(OllamaRuntimeMode.native, "http://127.0.0.1:11434", ["qwen2.5:3b"]))
    uc = SyncLocalOllamaProviderUC(runtime=runtime, ai_provider_repo=repo, provider_name="Локальная модель (Ollama)")

    result = await uc.execute()

    assert len(repo.items) == 1
    created = repo.items[0]
    assert created.type == AIProviderType.ollama
    assert created.base_url == "http://127.0.0.1:11434/v1"
    assert created.models == ["qwen2.5:3b"]
    assert created.api_key == ""
    assert result.provider_id == created.id


@pytest.mark.unit
async def test__sync__updates_existing_record_without_duplicating() -> None:
    repo = _FakeProviderRepo()
    runtime = _FakeRuntime(_status(OllamaRuntimeMode.docker, "http://127.0.0.1:11500", ["llama3.1:8b"]))
    uc = SyncLocalOllamaProviderUC(runtime=runtime, ai_provider_repo=repo, provider_name="Локальная модель (Ollama)")

    first = await uc.execute()
    runtime._status = _status(OllamaRuntimeMode.docker, "http://127.0.0.1:11500", ["llama3.1:8b", "qwen2.5:7b"])
    second = await uc.execute()

    assert len(repo.items) == 1
    assert first.provider_id == second.provider_id  # same record reused
    assert repo.items[0].models == ["llama3.1:8b", "qwen2.5:7b"]


@pytest.mark.unit
async def test__sync__runtime_down_keeps_existing_models() -> None:
    repo = _FakeProviderRepo()
    up = _FakeRuntime(_status(OllamaRuntimeMode.docker, "http://127.0.0.1:11434", ["qwen2.5:3b"]))
    await SyncLocalOllamaProviderUC(
        runtime=up, ai_provider_repo=repo, provider_name="Локальная модель (Ollama)"
    ).execute()

    # Runtime stopped: status can't list models. Must NOT wipe the known list.
    down = _FakeRuntime(_status(OllamaRuntimeMode.none, None, []))
    result = await SyncLocalOllamaProviderUC(
        runtime=down, ai_provider_repo=repo, provider_name="Локальная модель (Ollama)"
    ).execute()

    assert repo.items[0].models == ["qwen2.5:3b"]
    assert result.models == ["qwen2.5:3b"]


@pytest.mark.unit
async def test__sync__runtime_down_and_no_record_creates_nothing() -> None:
    repo = _FakeProviderRepo()
    down = _FakeRuntime(_status(OllamaRuntimeMode.none, None, []))

    result = await SyncLocalOllamaProviderUC(
        runtime=down, ai_provider_repo=repo, provider_name="Локальная модель (Ollama)"
    ).execute()

    assert repo.items == []
    assert result.provider_id is None
