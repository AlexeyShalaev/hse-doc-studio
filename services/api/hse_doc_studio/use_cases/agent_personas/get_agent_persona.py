from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.entities import AgentPersona
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import IAgentPersonaRepository


@dataclass
class GetAgentPersonaInput:
    persona_id: UUID


@dataclass
class GetAgentPersonaOutput:
    persona: AgentPersona


class GetAgentPersonaUC:
    def __init__(self, agent_persona_repo: IAgentPersonaRepository) -> None:
        self._repo = agent_persona_repo

    async def execute(self, inp: GetAgentPersonaInput) -> GetAgentPersonaOutput:
        persona = self._repo.get(inp.persona_id)
        if persona is None:
            raise NotFoundError(
                localized_error(f"Роль агента {inp.persona_id} не найдена", f"agent persona {inp.persona_id} not found")
            )
        return GetAgentPersonaOutput(persona=persona)
