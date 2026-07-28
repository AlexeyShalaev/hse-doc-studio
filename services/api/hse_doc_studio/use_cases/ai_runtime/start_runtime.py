from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.ai_runtime import IOllamaRuntime
from hse_doc_studio.core.entities import OllamaRuntimeStatus


@dataclass
class StartOllamaRuntimeResult:
    started: bool
    status: OllamaRuntimeStatus


class StartOllamaRuntimeUC:
    """Bring the local runtime up (adopt native, else start the container).

    Returns the resolved status so the UI can react (mode, base_url, models).
    `started` is False when neither a native server nor the managed container
    could be reached — e.g. the engine image isn't installed yet.
    """

    def __init__(self, runtime: IOllamaRuntime) -> None:
        self._runtime = runtime

    async def execute(self) -> StartOllamaRuntimeResult:
        base = await self._runtime.ensure_running()
        return StartOllamaRuntimeResult(started=base is not None, status=await self._runtime.status())
