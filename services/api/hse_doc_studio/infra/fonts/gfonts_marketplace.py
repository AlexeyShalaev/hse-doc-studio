from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from hse_doc_studio.core.fonts.entities import (
    FontCatalog,
    FontCatalogFile,
    MarketplaceFont,
    MarketplaceSearchResult,
)
from hse_doc_studio.core.fonts.repositories import IFontMarketplace

logger = structlog.get_logger()

_RAW_BASE = "https://raw.githubusercontent.com/google/fonts/main/"
_LICENSE_DIRS = ("ofl", "apache", "ufl")
_CONNECT_TIMEOUT_S = 30.0

# Google Fonts `category` → normalised token used by the UI filter.
_CATEGORY_MAP = {
    "serif": "serif",
    "sans serif": "sans-serif",
    "sans-serif": "sans-serif",
    "display": "display",
    "handwriting": "handwriting",
    "monospace": "monospace",
}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


@dataclass(frozen=True)
class _IndexEntry:
    id: str
    family: str
    category: str
    cyrillic: bool
    files: tuple[FontCatalogFile, ...]


def build_index(tree: dict[str, Any], metadata: dict[str, Any]) -> dict[str, _IndexEntry]:
    """Join the google/fonts file tree (static TTFs) with GF metadata (name +
    category + subsets), keyed by folder slug. Pure — no I/O, so it's testable.

    Only families that have at least one STATIC TTF in the repo are kept (variable
    fonts are excluded — XeLaTeX needs separate weight files)."""
    files_by_slug: dict[str, list[FontCatalogFile]] = {}
    for node in tree.get("tree", []):
        path = str(node.get("path", ""))
        if not path.lower().endswith(".ttf") or "[" in path:  # skip variable `Font[wght].ttf`
            continue
        parts = path.split("/")
        if len(parts) < 3 or parts[0] not in _LICENSE_DIRS:
            continue
        files_by_slug.setdefault(parts[1], []).append(FontCatalogFile(filename=parts[-1], url=_RAW_BASE + path))

    index: dict[str, _IndexEntry] = {}
    for fam in metadata.get("familyMetadataList", []):
        family = fam.get("family")
        if not family:
            continue
        slug = _slug(family)
        files = files_by_slug.get(slug)
        if not files:
            continue  # variable-only or not in repo → not installable for XeLaTeX
        subsets = fam.get("subsets") or []
        index[slug] = _IndexEntry(
            id=slug,
            family=family,
            category=_CATEGORY_MAP.get(str(fam.get("category", "")).strip().lower(), "other"),
            cyrillic="cyrillic" in subsets,
            files=tuple(sorted(files, key=lambda f: f.filename)),
        )
    return index


class GoogleFontsMarketplace(IFontMarketplace):
    """Searchable Google Fonts library, limited to families with static TTFs.

    Builds an in-memory index from two cached HTTP fetches (the github file tree
    + the GF metadata) refreshed on a TTL. Best-effort: if the fetches fail it
    serves the bundled curated catalog so search/install still work offline.
    """

    def __init__(
        self,
        metadata_url: str,
        tree_url: str,
        ttl_s: float,
        request_timeout_s: float,
        fallback: FontCatalog,
    ) -> None:
        self._metadata_url = metadata_url
        self._tree_url = tree_url
        self._ttl_s = ttl_s
        self._request_timeout_s = request_timeout_s
        self._fallback = fallback
        self._index: dict[str, _IndexEntry] | None = None
        self._built_at = 0.0
        self._lock = asyncio.Lock()

    async def _fetch_json(self, url: str) -> dict[str, Any]:
        timeout = httpx.Timeout(self._request_timeout_s, connect=_CONNECT_TIMEOUT_S)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers={"Accept": "application/json"})
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return data

    def _fallback_index(self) -> dict[str, _IndexEntry]:
        category_by_family = {"serif": "serif", "sans": "sans-serif", "mono": "monospace"}
        return {
            item.id: _IndexEntry(
                id=item.id,
                family=item.label,
                category=category_by_family.get(item.family, "other"),
                cyrillic=True,  # the curated set is all Cyrillic
                files=item.files,
            )
            for item in self._fallback.items
        }

    async def _ensure_index(self) -> dict[str, _IndexEntry]:
        if self._index is not None and (time.monotonic() - self._built_at) < self._ttl_s:
            return self._index
        async with self._lock:
            if self._index is not None and (time.monotonic() - self._built_at) < self._ttl_s:
                return self._index
            try:
                tree = await self._fetch_json(self._tree_url)
                metadata = await self._fetch_json(self._metadata_url)
                built = build_index(tree, metadata)
                if not built:
                    raise ValueError("empty index built from google/fonts")
                self._index = built
                logger.info("gfonts marketplace index built", families=len(built))
            except Exception as exc:  # noqa: BLE001 — degrade to the bundled set
                logger.warning("gfonts marketplace fetch failed, using fallback", exc=str(exc))
                if self._index is None:
                    self._index = self._fallback_index()
            self._built_at = time.monotonic()
            return self._index

    async def search(
        self, query: str, category: str | None, cyrillic_only: bool, limit: int, offset: int
    ) -> MarketplaceSearchResult:
        index = await self._ensure_index()
        q = query.strip().lower()
        items = [
            e
            for e in index.values()
            if (not cyrillic_only or e.cyrillic)
            and (not category or e.category == category)
            and (not q or q in e.family.lower())
        ]
        items.sort(key=lambda e: e.family.lower())
        page = items[max(0, offset) : max(0, offset) + max(0, limit)]
        return MarketplaceSearchResult(
            total=len(items),
            items=tuple(
                MarketplaceFont(
                    id=e.id, family=e.family, category=e.category, cyrillic=e.cyrillic, file_count=len(e.files)
                )
                for e in page
            ),
        )

    async def get_files(self, font_id: str) -> list[FontCatalogFile]:
        index = await self._ensure_index()
        entry = index.get(font_id)
        return list(entry.files) if entry else []
