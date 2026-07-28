from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderType
from hse_doc_studio.infra.persistence.ai_provider import JsonAIProviderRepository


def _make_provider(name: str = "OpenAI", api_key: str = "sk-secret") -> AIProvider:
    return AIProvider(
        id=uuid4(),
        name=name,
        type=AIProviderType.openai,
        api_key=api_key,
        base_url="",
        models=["gpt-4.1"],
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.unit
def test__ai_provider_repository__no_file__returns_empty(tmp_path: Path) -> None:
    repo = JsonAIProviderRepository(tmp_path)
    assert repo.list_all() == []


@pytest.mark.unit
def test__ai_provider_repository__create__roundtrips_via_new_instance(tmp_path: Path) -> None:
    provider = _make_provider()
    JsonAIProviderRepository(tmp_path).create(provider)

    # A fresh instance reads the same file — verifies persistence, not memory.
    loaded = JsonAIProviderRepository(tmp_path).get(provider.id)
    assert loaded is not None
    assert loaded.name == provider.name
    assert loaded.type == AIProviderType.openai
    assert loaded.api_key == "sk-secret"
    assert loaded.models == ["gpt-4.1"]


@pytest.mark.unit
def test__ai_provider_repository__update__replaces_record(tmp_path: Path) -> None:
    repo = JsonAIProviderRepository(tmp_path)
    provider = _make_provider(name="Old")
    repo.create(provider)

    updated = AIProvider(
        id=provider.id,
        name="New",
        type=provider.type,
        api_key=provider.api_key,
        base_url="https://api.example.com/v1",
        models=["m1", "m2"],
        created_at=provider.created_at,
    )
    repo.update(updated)

    loaded = repo.get(provider.id)
    assert loaded is not None
    assert loaded.name == "New"
    assert loaded.base_url == "https://api.example.com/v1"
    assert loaded.models == ["m1", "m2"]
    assert len(repo.list_all()) == 1


@pytest.mark.unit
def test__ai_provider_repository__delete__removes_record(tmp_path: Path) -> None:
    repo = JsonAIProviderRepository(tmp_path)
    provider = _make_provider()
    repo.create(provider)

    assert repo.delete(provider.id) is True
    assert repo.get(provider.id) is None
    assert repo.list_all() == []


@pytest.mark.unit
def test__ai_provider_repository__delete_missing__returns_false(tmp_path: Path) -> None:
    repo = JsonAIProviderRepository(tmp_path)
    assert repo.delete(uuid4()) is False


@pytest.mark.unit
def test__ai_provider_repository__corrupted_file__returns_empty(tmp_path: Path) -> None:
    (tmp_path / "ai_providers.json").write_text("not valid json{{", encoding="utf-8")
    assert JsonAIProviderRepository(tmp_path).list_all() == []


@pytest.mark.unit
def test__ai_provider_repository__connection_fields_roundtrip(tmp_path: Path) -> None:
    provider = AIProvider(
        id=uuid4(),
        name="Internal",
        type=AIProviderType.openai_compat,
        api_key="sk-x",
        base_url="https://internal/v1",
        models=[],
        created_at=datetime.now(timezone.utc),
        ssl_verify=False,
        connect_timeout_s=5.0,
        request_timeout_s=120.0,
    )
    JsonAIProviderRepository(tmp_path).create(provider)

    loaded = JsonAIProviderRepository(tmp_path).get(provider.id)
    assert loaded is not None
    assert loaded.ssl_verify is False
    assert loaded.connect_timeout_s == 5.0
    assert loaded.request_timeout_s == 120.0


@pytest.mark.unit
def test__ai_provider_repository__legacy_record_without_connection_fields__defaults(tmp_path: Path) -> None:
    # A record written before the connection fields existed must still load,
    # falling back to the safe defaults (verify on, 10s connect, 60s request).
    (tmp_path / "ai_providers.json").write_text(
        '[{"id": "11111111-1111-1111-1111-111111111111", "name": "Old", "type": "openai", '
        '"api_key": "sk", "base_url": "", "models": [], "created_at": "2024-01-01T00:00:00+00:00"}]',
        encoding="utf-8",
    )
    [loaded] = JsonAIProviderRepository(tmp_path).list_all()
    assert loaded.ssl_verify is True
    assert loaded.connect_timeout_s == 10.0
    assert loaded.request_timeout_s == 60.0
