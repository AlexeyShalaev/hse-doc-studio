from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.ai_catalog import ModelCatalog, ModelFit, recommend
from hse_doc_studio.core.ai_runtime import IHardwareProbe
from hse_doc_studio.core.entities import HardwareInfo
from hse_doc_studio.core.i18n import current_interface_language


@dataclass
class ListModelCatalogResult:
    hardware: HardwareInfo
    models: list[ModelFit]


class ListModelCatalogUC:
    """Return the curated local-model catalog annotated for the host hardware.

    Detects the hardware, then runs the pure `recommend()` domain logic to mark
    which models fit (GPU/CPU) and which single one to default to.
    """

    def __init__(self, hardware_probe: IHardwareProbe, catalog: ModelCatalog) -> None:
        self._probe = hardware_probe
        self._catalog = catalog

    async def execute(self) -> ListModelCatalogResult:
        hardware = await self._probe.detect()
        models = recommend(self._catalog, hardware, current_interface_language())
        return ListModelCatalogResult(hardware=hardware, models=models)
