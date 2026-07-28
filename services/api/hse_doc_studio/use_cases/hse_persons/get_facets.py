from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.hse_persons.entities import HseFacets
from hse_doc_studio.core.hse_persons.repositories import IHsePersonsGateway


@dataclass
class GetHseFacetsInput:
    campus: str = ""


class GetHseFacetsUC:
    def __init__(self, gateway: IHsePersonsGateway) -> None:
        self._gateway = gateway

    async def execute(self, inp: GetHseFacetsInput) -> HseFacets:
        return await self._gateway.get_facets(inp.campus)
