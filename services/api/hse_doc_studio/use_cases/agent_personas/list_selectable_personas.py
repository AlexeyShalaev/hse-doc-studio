from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.core.repositories import IAgentPersonaRepository
from hse_doc_studio.use_cases.chat.personas import CUSTOM_ID, list_personas


@dataclass
class SelectablePersona:
    id: str
    label: str
    description: str
    builtin: bool


@dataclass
class ListSelectablePersonasOutput:
    personas: list[SelectablePersona]


class ListSelectablePersonasUC:
    """Flat list of roles for the chat picker: built-in presets + user-defined
    custom roles. Order: Базовый → presets → user roles → inline «Своя роль»."""

    def __init__(self, agent_persona_repo: IAgentPersonaRepository) -> None:
        self._repo = agent_persona_repo

    async def execute(self) -> ListSelectablePersonasOutput:
        builtins = list_personas(current_interface_language())
        out: list[SelectablePersona] = [
            SelectablePersona(p.id, p.label, p.description, builtin=True) for p in builtins if p.id != CUSTOM_ID
        ]
        out.extend(SelectablePersona(str(p.id), p.label, p.description, builtin=False) for p in self._repo.list_all())
        # The inline free-text role (reveals a textarea in the UI) goes last.
        out.extend(SelectablePersona(p.id, p.label, p.description, builtin=True) for p in builtins if p.id == CUSTOM_ID)
        return ListSelectablePersonasOutput(personas=out)
