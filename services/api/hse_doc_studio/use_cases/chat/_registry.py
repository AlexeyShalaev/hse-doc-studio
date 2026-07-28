from __future__ import annotations

from collections.abc import Sequence

from hse_doc_studio.core.agent.entities import ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.enums import ToolKind


class ToolRegistry:
    """Table-driven tool lookup (thin, no framework — like the SDK dispatch).

    `specs(weak_model=...)` returns the schemas advertised to the model; for a
    weak/local model only the `weak_model_safe` subset is exposed so it is less
    likely to mis-call complex tools.
    """

    def __init__(self, definitions: Sequence[ToolDefinition]) -> None:
        self._by_name: dict[str, ToolDefinition] = {d.spec.name: d for d in definitions}

    def get(self, name: str) -> ToolDefinition | None:
        return self._by_name.get(name)

    def all(self) -> list[ToolDefinition]:
        return list(self._by_name.values())

    def kind(self, name: str) -> ToolKind | None:
        definition = self._by_name.get(name)
        return definition.kind if definition is not None else None

    def specs(
        self,
        *,
        weak_model: bool = False,
        allowed: frozenset[str] | None = None,
        has_project: bool = True,
    ) -> list[ToolSpec]:
        # `allowed` (None = no restriction) is the user's Configure-Tools choice;
        # `has_project=False` drops project-scoped tools (unified agent outside a project).
        return [
            d.spec
            for d in self._by_name.values()
            if (d.weak_model_safe or not weak_model)
            and (allowed is None or d.spec.name in allowed)
            and (has_project or not d.requires_project)
        ]

    def requires_project(self, name: str) -> bool:
        definition = self._by_name.get(name)
        return definition is None or definition.requires_project
