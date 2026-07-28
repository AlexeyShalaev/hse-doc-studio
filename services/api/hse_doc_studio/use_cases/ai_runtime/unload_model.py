from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.ai_runtime import IOllamaRuntime
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.use_cases.ai_runtime.model_ref import is_valid_model_ref


@dataclass
class UnloadModelInput:
    name: str


@dataclass
class UnloadModelResult:
    unloaded: bool


class UnloadModelUC:
    """Evict a model from memory now (keep_alive=0), freeing RAM/VRAM."""

    def __init__(self, runtime: IOllamaRuntime) -> None:
        self._runtime = runtime

    async def execute(self, inp: UnloadModelInput) -> UnloadModelResult:
        name = inp.name.strip()
        if not name:
            raise ValueError(localized_error("укажите название модели", "model name is required"))
        if not is_valid_model_ref(name):
            raise ValueError(localized_error(f"некорректное название модели: {name}", f"invalid model name: {name}"))
        return UnloadModelResult(unloaded=await self._runtime.unload_model(name))
