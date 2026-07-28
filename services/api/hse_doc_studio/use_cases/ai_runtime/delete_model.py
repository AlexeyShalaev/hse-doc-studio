from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.ai_runtime import IOllamaRuntime
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.use_cases.ai_runtime.model_ref import is_valid_model_ref


@dataclass
class DeleteOllamaModelInput:
    name: str


@dataclass
class DeleteOllamaModelResult:
    deleted: bool


class DeleteOllamaModelUC:
    """Remove an installed local model (any pulled tag — no allowlist needed)."""

    def __init__(self, runtime: IOllamaRuntime) -> None:
        self._runtime = runtime

    async def execute(self, inp: DeleteOllamaModelInput) -> DeleteOllamaModelResult:
        name = inp.name.strip()
        if not name:
            raise ValueError(localized_error("укажите название модели", "model name is required"))
        if not is_valid_model_ref(name):
            raise ValueError(localized_error(f"некорректное название модели: {name}", f"invalid model name: {name}"))
        return DeleteOllamaModelResult(deleted=await self._runtime.delete_model(name))
