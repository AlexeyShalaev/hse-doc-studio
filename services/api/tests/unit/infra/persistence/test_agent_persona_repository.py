from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from hse_doc_studio.core.entities import AgentPersona
from hse_doc_studio.infra.persistence.agent_persona import JsonAgentPersonaRepository


def _make_persona(label: str = "Ревьюер") -> AgentPersona:
    return AgentPersona(
        id=uuid4(),
        label=label,
        description="строгий ревьюер",
        instruction="Будь придирчивым ревьюером кода.",
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.unit
def test__agent_persona_repo__no_file__returns_empty(tmp_path: Path) -> None:
    assert JsonAgentPersonaRepository(tmp_path).list_all() == []


@pytest.mark.unit
def test__agent_persona_repo__create__roundtrips_via_new_instance(tmp_path: Path) -> None:
    persona = _make_persona()
    JsonAgentPersonaRepository(tmp_path).create(persona)

    loaded = JsonAgentPersonaRepository(tmp_path).get(persona.id)
    assert loaded is not None
    assert loaded.label == "Ревьюер"
    assert loaded.description == "строгий ревьюер"
    assert loaded.instruction == "Будь придирчивым ревьюером кода."
    assert (tmp_path / "agent_personas.json").exists()


@pytest.mark.unit
def test__agent_persona_repo__update__replaces_record(tmp_path: Path) -> None:
    repo = JsonAgentPersonaRepository(tmp_path)
    persona = _make_persona(label="Old")
    repo.create(persona)

    repo.update(
        AgentPersona(
            id=persona.id,
            label="New",
            description="d2",
            instruction="i2",
            created_at=persona.created_at,
        )
    )
    loaded = repo.get(persona.id)
    assert loaded is not None
    assert loaded.label == "New"
    assert loaded.instruction == "i2"
    assert len(repo.list_all()) == 1


@pytest.mark.unit
def test__agent_persona_repo__delete__removes_record(tmp_path: Path) -> None:
    repo = JsonAgentPersonaRepository(tmp_path)
    persona = _make_persona()
    repo.create(persona)

    assert repo.delete(persona.id) is True
    assert repo.get(persona.id) is None


@pytest.mark.unit
def test__agent_persona_repo__delete_missing__returns_false(tmp_path: Path) -> None:
    repo = JsonAgentPersonaRepository(tmp_path)

    assert repo.delete(uuid4()) is False


@pytest.mark.unit
def test__agent_persona_repo__corrupted_file__returns_empty(tmp_path: Path) -> None:
    (tmp_path / "agent_personas.json").write_text("not json{{", encoding="utf-8")
    assert JsonAgentPersonaRepository(tmp_path).list_all() == []
