from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.entities import AgentPersona
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import IAgentPersonaRepository


@dataclass
class UpdateAgentPersonaInput:
    persona_id: UUID
    # None → keep the stored value (PATCH semantics).
    label: str | None = None
    description: str | None = None
    instruction: str | None = None


@dataclass
class UpdateAgentPersonaOutput:
    persona: AgentPersona


class UpdateAgentPersonaUC:
    def __init__(self, agent_persona_repo: IAgentPersonaRepository) -> None:
        self._repo = agent_persona_repo

    async def execute(self, inp: UpdateAgentPersonaInput) -> UpdateAgentPersonaOutput:
        existing = self._repo.get(inp.persona_id)
        if existing is None:
            raise NotFoundError(
                localized_error(f"Роль агента {inp.persona_id} не найдена", f"agent persona {inp.persona_id} not found")
            )

        label = existing.label if inp.label is None else inp.label.strip()
        if not label:
            raise ValueError(localized_error("Название обязательно", "label is required"))
        instruction = existing.instruction if inp.instruction is None else inp.instruction.strip()
        if not instruction:
            raise ValueError(localized_error("Инструкция обязательна", "instruction is required"))

        updated = AgentPersona(
            id=existing.id,
            label=label,
            description=existing.description if inp.description is None else inp.description.strip(),
            instruction=instruction,
            created_at=existing.created_at,
        )
        self._repo.update(updated)
        return UpdateAgentPersonaOutput(persona=updated)
