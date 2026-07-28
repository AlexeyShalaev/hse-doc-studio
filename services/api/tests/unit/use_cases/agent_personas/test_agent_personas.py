from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.entities import AgentPersona
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.use_cases.agent_personas.create_agent_persona import (
    CreateAgentPersonaInput,
    CreateAgentPersonaUC,
)
from hse_doc_studio.use_cases.agent_personas.delete_agent_persona import (
    DeleteAgentPersonaInput,
    DeleteAgentPersonaUC,
)
from hse_doc_studio.use_cases.agent_personas.list_selectable_personas import ListSelectablePersonasUC
from hse_doc_studio.use_cases.agent_personas.update_agent_persona import (
    UpdateAgentPersonaInput,
    UpdateAgentPersonaUC,
)


class _FakeRepo:
    def __init__(self) -> None:
        self._items: dict[UUID, AgentPersona] = {}

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


@pytest.mark.unit
async def test__create_agent_persona__persists_and_trims() -> None:
    repo = _FakeRepo()
    out = await CreateAgentPersonaUC(repo).execute(
        CreateAgentPersonaInput(label="  Ревьюер  ", instruction="  Будь строгим  ", description="x")
    )
    assert out.persona.label == "Ревьюер"
    assert out.persona.instruction == "Будь строгим"
    assert out.persona.id in {p.id for p in repo.list_all()}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("label", "instruction", "match"),
    [
        ("   ", "x", "Название"),
        ("x", "   ", "Инструкция"),
    ],
)
async def test__create_agent_persona__blank_label_or_instruction__raises(
    label: str, instruction: str, match: str
) -> None:
    uc = CreateAgentPersonaUC(_FakeRepo())

    with pytest.raises(ValueError, match=match):
        await uc.execute(CreateAgentPersonaInput(label=label, instruction=instruction))


@pytest.mark.unit
async def test__update_agent_persona__patch_keeps_unset_fields() -> None:
    repo = _FakeRepo()
    persona = AgentPersona(
        id=uuid4(), label="A", description="d", instruction="i", created_at=datetime.now(timezone.utc)
    )
    repo.create(persona)

    out = await UpdateAgentPersonaUC(repo).execute(UpdateAgentPersonaInput(persona_id=persona.id, label="B"))
    assert out.persona.label == "B"
    assert out.persona.instruction == "i"  # untouched
    assert out.persona.description == "d"


@pytest.mark.unit
async def test__update_agent_persona__missing__raises() -> None:
    with pytest.raises(NotFoundError, match="не найдена"):
        await UpdateAgentPersonaUC(_FakeRepo()).execute(UpdateAgentPersonaInput(persona_id=uuid4(), label="x"))


@pytest.mark.unit
async def test__delete_agent_persona__missing__raises() -> None:
    with pytest.raises(NotFoundError, match="не найдена"):
        await DeleteAgentPersonaUC(_FakeRepo()).execute(DeleteAgentPersonaInput(persona_id=uuid4()))


@pytest.mark.unit
async def test__list_selectable_personas__merges_builtins_and_custom() -> None:
    repo = _FakeRepo()
    custom = AgentPersona(
        id=uuid4(), label="Мой ревьюер", description="d", instruction="i", created_at=datetime.now(timezone.utc)
    )
    repo.create(custom)

    out = await ListSelectablePersonasUC(repo).execute()
    by_id = {p.id: p for p in out.personas}

    # Built-in presets are present and flagged builtin.
    assert by_id["default"].builtin is True
    assert by_id["methodologist"].builtin is True
    # The user role is present and flagged custom.
    assert by_id[str(custom.id)].builtin is False
    assert by_id[str(custom.id)].label == "Мой ревьюер"
    # The inline free-text "custom" role is last.
    assert out.personas[-1].id == "custom"
