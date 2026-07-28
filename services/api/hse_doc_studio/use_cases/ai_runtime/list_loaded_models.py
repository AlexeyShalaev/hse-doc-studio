from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.ai_runtime import IOllamaRuntime
from hse_doc_studio.core.entities import LoadedModel


@dataclass
class ListLoadedModelsResult:
    models: list[LoadedModel]


class ListLoadedModelsUC:
    """List models currently held in memory by Ollama (the UI polls this)."""

    def __init__(self, runtime: IOllamaRuntime) -> None:
        self._runtime = runtime

    async def execute(self) -> ListLoadedModelsResult:
        return ListLoadedModelsResult(models=await self._runtime.list_loaded_models())
