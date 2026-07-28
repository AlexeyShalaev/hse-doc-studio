from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.fonts.entities import MarketplaceSearchResult
from hse_doc_studio.core.fonts.repositories import IFontMarketplace


@dataclass
class SearchMarketplaceInput:
    query: str = ""
    category: str | None = None
    cyrillic_only: bool = True
    limit: int = 30
    offset: int = 0


@dataclass
class SearchMarketplaceOutput:
    result: MarketplaceSearchResult


class SearchMarketplaceUC:
    def __init__(self, marketplace: IFontMarketplace) -> None:
        self._marketplace = marketplace

    async def execute(self, inp: SearchMarketplaceInput) -> SearchMarketplaceOutput:
        result = await self._marketplace.search(
            query=inp.query,
            category=inp.category,
            cyrillic_only=inp.cyrillic_only,
            limit=inp.limit,
            offset=inp.offset,
        )
        return SearchMarketplaceOutput(result=result)
