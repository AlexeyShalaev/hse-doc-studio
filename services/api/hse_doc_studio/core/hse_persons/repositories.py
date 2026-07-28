from __future__ import annotations

from typing import Protocol

from hse_doc_studio.core.hse_persons.entities import (
    HseFacets,
    HsePersonDetail,
    HsePersonQuery,
    HseSearchResult,
)


class IHsePersonsGateway(Protocol):
    """Read-only access to the public HSE staff directory (hse.ru/org/persons).

    Implementations scrape the server-rendered directory politely (honouring the
    site's declared crawl-delay, with caching and graceful degradation) and MUST
    never raise on network/parse failure — searches degrade to empty results and
    detail lookups to ``None`` so the UI keeps working when hse.ru is unreachable."""

    async def search(self, query: HsePersonQuery) -> HseSearchResult: ...

    async def get_detail(self, person_id: str) -> HsePersonDetail | None: ...

    async def get_facets(self, campus: str) -> HseFacets: ...
