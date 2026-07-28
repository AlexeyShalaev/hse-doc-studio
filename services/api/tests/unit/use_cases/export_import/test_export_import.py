from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.entities import AgentPersona, AIProvider
from hse_doc_studio.core.enums import AIProviderType
from hse_doc_studio.core.export_import.serialization import persona_to_export_dict, provider_to_export_dict
from hse_doc_studio.use_cases.export_import.export_data import ExportDataInput, ExportDataUC
from hse_doc_studio.use_cases.export_import.import_data import ImportDataInput, ImportDataUC


class _FakeProviderRepo:
    def __init__(self, items: list[AIProvider] | None = None) -> None:
        self._items: dict[UUID, AIProvider] = {p.id: p for p in (items or [])}

    def list_all(self) -> list[AIProvider]:
        return list(self._items.values())

    def get(self, provider_id: UUID) -> AIProvider | None:
        return self._items.get(provider_id)

    def create(self, provider: AIProvider) -> None:
        self._items[provider.id] = provider

    def update(self, provider: AIProvider) -> None:
        self._items[provider.id] = provider

    def delete(self, provider_id: UUID) -> bool:
        return self._items.pop(provider_id, None) is not None


class _FakePersonaRepo:
    def __init__(self, items: list[AgentPersona] | None = None) -> None:
        self._items: dict[UUID, AgentPersona] = {p.id: p for p in (items or [])}

    def list_all(self) -> list[AgentPersona]:
        return list(self._items.values())

    def get(self, persona_id: UUID) -> AgentPersona | None:
        return self._items.get(persona_id)

    def create(self, persona: AgentPersona) -> None:
        self._items[persona.id] = persona

    def update(self, persona: AgentPersona) -> None:
        self._items[persona.id] = persona

    def delete(self, persona_id: UUID) -> bool:
        return self._items.pop(persona_id, None) is not None


class _FakeSettingsRepo:
    def __init__(self, data: dict[str, object] | None = None) -> None:
        self._data: dict[str, object] = dict(data or {})

    def get(self) -> dict[str, object]:
        return dict(self._data)

    def save(self, settings: dict[str, object]) -> None:
        self._data = dict(settings)


def _provider(
    name: str = "OpenAI",
    type_: AIProviderType = AIProviderType.openai,
    api_key: str = "sk-x",
    pid: UUID | None = None,
) -> AIProvider:
    return AIProvider(
        id=pid or uuid4(),
        name=name,
        type=type_,
        api_key=api_key,
        base_url="",
        models=["gpt-4"],
        created_at=datetime.now(timezone.utc),
    )


def _persona(label: str = "Ревьюер", pid: UUID | None = None) -> AgentPersona:
    return AgentPersona(
        id=pid or uuid4(),
        label=label,
        description="d",
        instruction="Будь строгим ревьюером.",
        created_at=datetime.now(timezone.utc),
    )


def _export_uc(
    settings: _FakeSettingsRepo,
    providers: _FakeProviderRepo,
    personas: _FakePersonaRepo | None = None,
) -> ExportDataUC:
    return ExportDataUC(settings, providers, personas or _FakePersonaRepo())


def _import_uc(
    settings: _FakeSettingsRepo,
    providers: _FakeProviderRepo,
    personas: _FakePersonaRepo | None = None,
) -> ImportDataUC:
    return ImportDataUC(settings, providers, personas or _FakePersonaRepo())


@pytest.mark.unit
async def test__export__excludes_ollama_and_keeps_settings() -> None:
    repo = _FakeProviderRepo(
        [_provider(name="OpenAI"), _provider(name="Local", type_=AIProviderType.ollama, api_key="")]
    )
    out = await _export_uc(_FakeSettingsRepo({"theme": "light"}), repo).execute(ExportDataInput())

    assert out.settings is not None
    assert out.settings["theme"] == "light"
    assert [p["name"] for p in out.ai_providers] == ["OpenAI"]  # ollama is auto-managed → excluded
    assert out.encrypted is False
    assert out.ai_providers[0]["api_key"] == "sk-x"  # plaintext export


@pytest.mark.unit
async def test__export__flags_off__empty_bundle() -> None:
    out = await _export_uc(_FakeSettingsRepo({"theme": "dark"}), _FakeProviderRepo([_provider()])).execute(
        ExportDataInput(include_settings=False, include_ai_providers=False)
    )

    assert out.settings is None
    assert out.ai_providers == []


@pytest.mark.unit
async def test__export_encrypted__no_provider_keys__not_marked_encrypted() -> None:
    # A password but nothing to encrypt (blank-key provider) must yield a PLAIN
    # bundle — otherwise import would accept any password (nothing to verify).
    repo = _FakeProviderRepo([_provider(name="Blank", api_key="")])
    out = await _export_uc(_FakeSettingsRepo({"theme": "dark"}), repo).execute(
        ExportDataInput(encryption_password="pw")
    )

    assert out.encrypted is False
    assert out.ai_providers[0]["api_key"] == ""


@pytest.mark.unit
async def test__export_encrypted__providers_excluded__not_marked_encrypted() -> None:
    repo = _FakeProviderRepo([_provider(api_key="sk-x")])
    out = await _export_uc(_FakeSettingsRepo(), repo).execute(
        ExportDataInput(include_ai_providers=False, encryption_password="pw")
    )

    assert out.encrypted is False
    assert out.ai_providers == []


@pytest.mark.unit
async def test__export_encrypted_then_import__round_trips_api_key() -> None:
    src = _FakeProviderRepo([_provider(name="OpenAI", api_key="sk-secret")])
    exported = await _export_uc(_FakeSettingsRepo(), src).execute(ExportDataInput(encryption_password="hunter2"))
    assert exported.encrypted is True
    assert exported.ai_providers[0]["api_key"] != "sk-secret"  # ciphertext, not plaintext

    dst = _FakeProviderRepo()
    result = await _import_uc(_FakeSettingsRepo(), dst).execute(
        ImportDataInput(encrypted=True, ai_providers=exported.ai_providers, decryption_password="hunter2")
    )

    assert result.ai_providers_imported == 1
    assert dst.list_all()[0].api_key == "sk-secret"


@pytest.mark.unit
async def test__import_encrypted__missing_password__raises() -> None:
    with pytest.raises(ValueError, match="зашифрован"):
        await _import_uc(_FakeSettingsRepo(), _FakeProviderRepo()).execute(
            ImportDataInput(encrypted=True, ai_providers=[{"name": "x"}])
        )


@pytest.mark.unit
async def test__import_encrypted__wrong_password__raises_and_changes_nothing() -> None:
    src = _FakeProviderRepo([_provider(api_key="sk-secret")])
    exported = await _export_uc(_FakeSettingsRepo(), src).execute(ExportDataInput(encryption_password="right"))

    dst_providers = _FakeProviderRepo()
    dst_settings = _FakeSettingsRepo({"theme": "dark"})
    with pytest.raises(ValueError, match="Неверный пароль"):
        await _import_uc(dst_settings, dst_providers).execute(
            ImportDataInput(
                encrypted=True,
                settings={"theme": "light"},
                ai_providers=exported.ai_providers,
                decryption_password="wrong",
            )
        )

    # Atomic: a wrong password applies neither providers nor settings.
    assert dst_providers.list_all() == []
    assert dst_settings.get()["theme"] == "dark"


@pytest.mark.unit
async def test__import_skip__keeps_existing_by_id() -> None:
    pid = uuid4()
    dst = _FakeProviderRepo([_provider(name="Old", api_key="sk-old", pid=pid)])
    incoming = provider_to_export_dict(_provider(name="New", api_key="sk-new", pid=pid))

    result = await _import_uc(_FakeSettingsRepo(), dst).execute(
        ImportDataInput(encrypted=False, ai_providers=[incoming], merge_strategy="skip")
    )

    assert result.ai_providers_skipped == 1
    kept = dst.get(pid)
    assert kept is not None
    assert kept.name == "Old"


@pytest.mark.unit
async def test__import_replace__overwrites_in_place_preserving_id() -> None:
    pid = uuid4()
    dst = _FakeProviderRepo([_provider(name="Old", api_key="sk-old", pid=pid)])
    incoming = provider_to_export_dict(_provider(name="New", api_key="sk-new", pid=pid))

    result = await _import_uc(_FakeSettingsRepo(), dst).execute(
        ImportDataInput(encrypted=False, ai_providers=[incoming], merge_strategy="replace")
    )

    assert result.ai_providers_imported == 1
    replaced = dst.get(pid)
    assert replaced is not None
    assert replaced.name == "New"
    assert replaced.api_key == "sk-new"


@pytest.mark.unit
async def test__import_settings__merges_known_keys_only() -> None:
    settings = _FakeSettingsRepo({"theme": "dark", "default_engine": "xelatex"})

    result = await _import_uc(settings, _FakeProviderRepo()).execute(
        ImportDataInput(encrypted=False, settings={"theme": "light", "bogus": "x"})
    )

    assert result.settings_imported is True
    saved = settings.get()
    assert saved["theme"] == "light"  # known key applied
    assert saved["default_engine"] == "xelatex"  # untouched key preserved
    assert "bogus" not in saved  # unknown key dropped


@pytest.mark.unit
async def test__export__includes_agent_personas() -> None:
    personas = _FakePersonaRepo([_persona(label="Мой ревьюер")])
    out = await _export_uc(_FakeSettingsRepo(), _FakeProviderRepo(), personas).execute(ExportDataInput())
    assert [p["label"] for p in out.agent_personas] == ["Мой ревьюер"]


@pytest.mark.unit
async def test__export__personas_flag_off__excluded() -> None:
    personas = _FakePersonaRepo([_persona()])
    out = await _export_uc(_FakeSettingsRepo(), _FakeProviderRepo(), personas).execute(
        ExportDataInput(include_agent_personas=False)
    )
    assert out.agent_personas == []


@pytest.mark.unit
async def test__export_then_import__round_trips_persona_preserving_id() -> None:
    pid = uuid4()
    src = _FakePersonaRepo([_persona(label="Source role", pid=pid)])
    exported = await _export_uc(_FakeSettingsRepo(), _FakeProviderRepo(), src).execute(ExportDataInput())

    dst = _FakePersonaRepo()
    result = await _import_uc(_FakeSettingsRepo(), _FakeProviderRepo(), dst).execute(
        ImportDataInput(encrypted=False, agent_personas=exported.agent_personas)
    )

    assert result.agent_personas_imported == 1
    loaded = dst.get(pid)
    assert loaded is not None
    assert loaded.label == "Source role"


@pytest.mark.unit
async def test__import_persona_skip__keeps_existing_by_id() -> None:
    pid = uuid4()
    dst = _FakePersonaRepo([_persona(label="Old", pid=pid)])
    incoming = persona_to_export_dict(_persona(label="New", pid=pid))

    result = await _import_uc(_FakeSettingsRepo(), _FakeProviderRepo(), dst).execute(
        ImportDataInput(encrypted=False, agent_personas=[incoming], merge_strategy="skip")
    )

    assert result.agent_personas_skipped == 1
    kept = dst.get(pid)
    assert kept is not None
    assert kept.label == "Old"
