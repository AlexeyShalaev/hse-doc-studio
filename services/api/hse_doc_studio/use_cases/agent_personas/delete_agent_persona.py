from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import IAgentPersonaRepository


@dataclass
class DeleteAgentPersonaInput:
    persona_id: UUID


class DeleteAgentPersonaUC:
    def __init__(self, agent_persona_repo: IAgentPersonaRepository) -> None:
        self._repo = agent_persona_repo

    async def execute(self, inp: DeleteAgentPersonaInput) -> None:
        deleted = self._repo.delete(inp.persona_id)
        if not deleted:
            raise NotFoundError(
                localized_error(f"Роль агента {inp.persona_id} не найдена", f"agent persona {inp.persona_id} not found")
            )
