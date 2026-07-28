from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.entities import AgentPersona
from hse_doc_studio.core.repositories import IAgentPersonaRepository


@dataclass
class ListAgentPersonasOutput:
    personas: list[AgentPersona]


class ListAgentPersonasUC:
    def __init__(self, agent_persona_repo: IAgentPersonaRepository) -> None:
        self._repo = agent_persona_repo

    async def execute(self) -> ListAgentPersonasOutput:
        return ListAgentPersonasOutput(personas=self._repo.list_all())
