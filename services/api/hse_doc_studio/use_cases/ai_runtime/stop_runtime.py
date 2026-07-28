from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.ai_runtime import IOllamaRuntime
from hse_doc_studio.core.entities import OllamaRuntimeStatus


@dataclass
class StopOllamaRuntimeResult:
    stopped: bool
    detail: str | None
    status: OllamaRuntimeStatus


class StopOllamaRuntimeUC:
    """Stop the managed container (no-op for a native runtime we don't own)."""

    def __init__(self, runtime: IOllamaRuntime) -> None:
        self._runtime = runtime

    async def execute(self) -> StopOllamaRuntimeResult:
        stopped, detail = await self._runtime.stop()
        return StopOllamaRuntimeResult(stopped=stopped, detail=detail, status=await self._runtime.status())
