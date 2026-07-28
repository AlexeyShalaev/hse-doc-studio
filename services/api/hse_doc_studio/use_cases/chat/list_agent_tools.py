from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.use_cases.chat._registry import ToolRegistry


@dataclass
class AgentToolInfo:
    name: str
    description: str
    kind: str  # read | write | exec
    # False = an app/system tool usable without a project; the unified agent
    # hides project-only tools when the chat isn't bound to a project.
    requires_project: bool


@dataclass
class ListAgentToolsOutput:
    tools: list[AgentToolInfo]


class ListAgentToolsUC:
    """The agent's tool catalog, for the Configure-Tools UI (name/desc/kind)."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def execute(self) -> ListAgentToolsOutput:
        return ListAgentToolsOutput(
            tools=[
                AgentToolInfo(
                    name=d.spec.name,
                    description=d.spec.description,
                    kind=d.kind.value,
                    requires_project=d.requires_project,
                )
                for d in self._registry.all()
            ]
        )
