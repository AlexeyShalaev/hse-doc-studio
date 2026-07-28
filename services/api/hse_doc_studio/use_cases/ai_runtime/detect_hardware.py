from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.ai_runtime import IHardwareProbe
from hse_doc_studio.core.entities import HardwareInfo


@dataclass
class DetectHardwareResult:
    hardware: HardwareInfo


class DetectHardwareUC:
    """Detect the host's GPU/RAM/CPU so the UI can size local-model picks."""

    def __init__(self, hardware_probe: IHardwareProbe) -> None:
        self._probe = hardware_probe

    async def execute(self) -> DetectHardwareResult:
        return DetectHardwareResult(hardware=await self._probe.detect())
