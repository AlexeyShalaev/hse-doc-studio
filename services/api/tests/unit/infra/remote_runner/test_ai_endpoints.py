from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderType
from hse_doc_studio.core.remote_runner import RemoteAiEndpointChoice, RemoteRunnerSettings
from hse_doc_studio.infra.persistence.ai_provider import JsonAIProviderRepository
from hse_doc_studio.infra.remote_runner.ai_endpoints import LocalAiEndpointResolver
from hse_doc_studio.infra.remote_runner.supervisor import RemoteRunnerSupervisor
from hse_doc_studio.infra.runner.pairing_client import RunnerPairingClient
from hse_doc_studio.use_cases.remote_runner.update_remote_runner import UpdateRemoteRunnerInput, UpdateRemoteRunnerUC

from tests.unit.infra.remote_runner.fake_pairing_api import FakePairingServer
from tests.unit.infra.remote_runner.fakes import FakeSessions, MemorySettingsStore, eventually, save_identity

_URL = "https://studio.example.org"


def _provider(kind: AIProviderType, base_url: str, *, key: str = "") -> AIProvider:
    return AIProvider(
        id=uuid4(),
        name=f"{kind.value} provider",
        type=kind,
        api_key=key,
        base_url=base_url,
        models=["m"],
        created_at=datetime.now(UTC),
    )


async def _repo(tmp_path: Path, *providers: AIProvider) -> JsonAIProviderRepository:
    repo = JsonAIProviderRepository(tmp_path)
    for provider in providers:
        await repo.create(provider)
    return repo


async def test__resolver__keeps_local_providers_with_key_and_flavor(tmp_path: Path) -> None:
    ollama = _provider(AIProviderType.ollama, "http://localhost:11434/v1")
    lmstudio = _provider(AIProviderType.openai_compat, "http://localhost:1234/v1", key="sk-local")
    resolver = LocalAiEndpointResolver(await _repo(tmp_path, ollama, lmstudio))

    endpoints = await resolver(
        (
            RemoteAiEndpointChoice(name="ollama", provider_id=str(ollama.id)),
            RemoteAiEndpointChoice(name="lmstudio", provider_id=str(lmstudio.id)),
        )
    )

    assert [(e.name, e.flavor, e.display_url) for e in endpoints] == [
        ("ollama", "ollama", "http://localhost:11434/v1"),
        ("lmstudio", "openai", "http://localhost:1234/v1"),
    ]
    assert endpoints[1].api_key() == "sk-local"
    assert endpoints[0].api_key() is None


async def test__resolver__drops_missing_and_public_providers(tmp_path: Path) -> None:
    public = _provider(AIProviderType.openai_compat, "https://openrouter.ai/api/v1")
    resolver = LocalAiEndpointResolver(await _repo(tmp_path, public))

    endpoints = await resolver(
        (
            RemoteAiEndpointChoice(name="gone", provider_id=str(uuid4())),
            RemoteAiEndpointChoice(name="public", provider_id=str(public.id)),
        )
    )

    assert endpoints == ()


def _supervisor(tmp_path: Path, repo: JsonAIProviderRepository, sessions: FakeSessions) -> RemoteRunnerSupervisor:
    runner_dir = tmp_path / "remote-runner"
    save_identity(runner_dir, _URL)
    server = FakePairingServer()
    return RemoteRunnerSupervisor(
        MemorySettingsStore(RemoteRunnerSettings(enabled=True, server_url=_URL)),
        runner_dir=runner_dir,
        default_name="studio-mac",
        pairing_client=lambda url: RunnerPairingClient(url, version="0.3.0", transport=server.transport()),
        session_factory=sessions,
        ai_endpoints=LocalAiEndpointResolver(repo),
    )


async def test__update__choose_models__reannounces_without_restart_and_shows_urls(tmp_path: Path) -> None:
    ollama = _provider(AIProviderType.ollama, "http://localhost:11434/v1")
    repo = await _repo(tmp_path, ollama)
    sessions = FakeSessions()
    supervisor = _supervisor(tmp_path, repo, sessions)
    await supervisor.start()
    await eventually(lambda: len(sessions.sessions) == 1)
    uc = UpdateRemoteRunnerUC(supervisor, repo)

    status = await uc.execute(
        UpdateRemoteRunnerInput(ai_endpoints=(RemoteAiEndpointChoice(name="ollama", provider_id=str(ollama.id)),))
    )

    assert [(e.name, e.url) for e in status.ai_endpoints] == [("ollama", "http://localhost:11434/v1")]
    assert sessions.sessions[0].announced == [("ollama",)]
    assert len(sessions.specs) == 1
    await supervisor.stop()


async def test__update__public_provider__rejected(tmp_path: Path) -> None:
    public = _provider(AIProviderType.openai_compat, "https://api.example.com/v1")
    repo = await _repo(tmp_path, public)
    supervisor = _supervisor(tmp_path, repo, FakeSessions())
    await supervisor.start()

    with pytest.raises(ValueError, match="cannot be opened"):
        await UpdateRemoteRunnerUC(supervisor, repo).execute(
            UpdateRemoteRunnerInput(ai_endpoints=(RemoteAiEndpointChoice(name="api", provider_id=str(public.id)),))
        )
    await supervisor.stop()


async def test__new_session__carries_resolved_endpoints(tmp_path: Path) -> None:
    ollama = _provider(AIProviderType.ollama, "http://localhost:11434/v1")
    repo = await _repo(tmp_path, ollama)
    sessions = FakeSessions()
    supervisor = _supervisor(tmp_path, repo, sessions)
    await supervisor.start()
    await UpdateRemoteRunnerUC(supervisor, repo).execute(
        UpdateRemoteRunnerInput(
            concurrency=2, ai_endpoints=(RemoteAiEndpointChoice(name="ollama", provider_id=str(ollama.id)),)
        )
    )

    await eventually(lambda: bool(sessions.specs) and sessions.specs[-1].concurrency == 2)
    assert [e.name for e in sessions.specs[-1].ai_endpoints] == ["ollama"]
    await supervisor.stop()
