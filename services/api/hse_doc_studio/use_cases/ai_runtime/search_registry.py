from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.ai_runtime import IOllamaRegistry
from hse_doc_studio.core.entities import RegistryModel


@dataclass
class SearchRegistryInput:
    query: str


@dataclass
class SearchRegistryResult:
    models: list[RegistryModel]


class SearchRegistryUC:
    """Search the public Ollama registry for models to install (best-effort)."""

    def __init__(self, registry: IOllamaRegistry) -> None:
        self._registry = registry

    async def execute(self, inp: SearchRegistryInput) -> SearchRegistryResult:
        return SearchRegistryResult(models=await self._registry.search(inp.query))
