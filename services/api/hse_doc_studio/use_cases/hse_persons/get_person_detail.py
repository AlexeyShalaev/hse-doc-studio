from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.hse_persons.entities import HsePersonDetail
from hse_doc_studio.core.hse_persons.repositories import IHsePersonsGateway


@dataclass
class GetHsePersonDetailInput:
    person_id: str


class GetHsePersonDetailUC:
    def __init__(self, gateway: IHsePersonsGateway) -> None:
        self._gateway = gateway

    async def execute(self, inp: GetHsePersonDetailInput) -> HsePersonDetail | None:
        return await self._gateway.get_detail(inp.person_id)
