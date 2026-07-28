from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from hse_doc_studio.core.entities import AgentPersona
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import IAgentPersonaRepository


@dataclass
class CreateAgentPersonaInput:
    label: str
    instruction: str
    description: str = ""


@dataclass
class CreateAgentPersonaOutput:
    persona: AgentPersona


class CreateAgentPersonaUC:
    def __init__(self, agent_persona_repo: IAgentPersonaRepository) -> None:
        self._repo = agent_persona_repo

    async def execute(self, inp: CreateAgentPersonaInput) -> CreateAgentPersonaOutput:
        label = inp.label.strip()
        if not label:
            raise ValueError(localized_error("Название обязательно", "label is required"))
        instruction = inp.instruction.strip()
        if not instruction:
            raise ValueError(localized_error("Инструкция обязательна", "instruction is required"))
        persona = AgentPersona(
            id=uuid4(),
            label=label,
            description=inp.description.strip(),
            instruction=instruction,
            created_at=datetime.now(timezone.utc),
        )
        self._repo.create(persona)
        return CreateAgentPersonaOutput(persona=persona)
