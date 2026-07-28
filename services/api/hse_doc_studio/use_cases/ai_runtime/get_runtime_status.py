from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.ai_runtime import IOllamaRuntime
from hse_doc_studio.core.entities import OllamaRuntimeStatus


@dataclass
class GetOllamaStatusResult:
    status: OllamaRuntimeStatus


class GetOllamaStatusUC:
    """Resolve the current local-runtime status (native / docker / none)."""

    def __init__(self, runtime: IOllamaRuntime) -> None:
        self._runtime = runtime

    async def execute(self) -> GetOllamaStatusResult:
        return GetOllamaStatusResult(status=await self._runtime.status())
