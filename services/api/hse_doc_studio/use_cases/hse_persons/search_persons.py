from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.hse_persons.entities import HsePersonQuery, HseSearchResult
from hse_doc_studio.core.hse_persons.repositories import IHsePersonsGateway


@dataclass
class SearchHsePersonsInput:
    name: str = ""
    campus: str = ""
    udept: str = ""
    ltr: str = ""
    category: str = ""
    scirank: str = ""
    position: str = ""
    intst: str = ""
    limit: int = 40


class SearchHsePersonsUC:
    def __init__(self, gateway: IHsePersonsGateway) -> None:
        self._gateway = gateway

    async def execute(self, inp: SearchHsePersonsInput) -> HseSearchResult:
        return await self._gateway.search(
            HsePersonQuery(
                name=inp.name,
                campus=inp.campus,
                udept=inp.udept,
                ltr=inp.ltr,
                category=inp.category,
                scirank=inp.scirank,
                position=inp.position,
                intst=inp.intst,
                limit=inp.limit,
            )
        )
