"""Polite HTTP gateway to the public HSE staff directory.

The directory is scraped server-side with strict etiquette so we never risk
hammering the university's site:

* a **global min-interval gate** (default 3s) honours the site's declared
  ``Crawl-delay: 3`` — every outbound request waits its turn behind the gate;
* a **bounded concurrency** semaphore is a second guard;
* **three TTL caches** (list page / profile / facets) mean repeat interactions
  never touch hse.ru;
* **timeouts + bounded retries** (honouring ``Retry-After``) and **graceful
  degradation** — any failure yields an empty result / ``None``, never a 500.

Only robots-allowed URLs are used: ``/org/persons/?<facets>`` and
``/org/persons/<id>``. The disallowed ``search_person`` box is never used — the
name is applied as a local substring filter over the returned cards instead.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Generic, TypeVar
from urllib.parse import quote

import httpx
import structlog

from hse_doc_studio.core.hse_persons.entities import (
    HseFacets,
    HsePersonDetail,
    HsePersonQuery,
    HseSearchResult,
)
from hse_doc_studio.infra.hse_persons import parser

logger = structlog.get_logger()

_LETTER_RE = re.compile(r"[A-Za-zА-Яа-яЁё]")
_MAX_INTEREST_CHIPS = 60

_T = TypeVar("_T")


def _normalize(text: str) -> str:
    """Casefold and fold ё→е for a diacritic-insensitive substring match."""
    return text.casefold().replace("ё", "е")


class _TTLCache(Generic[_T]):
    """A minimal monotonic-clock TTL cache (mirrors the fonts marketplace index)."""

    def __init__(self, ttl_s: float) -> None:
        self._ttl = ttl_s
        self._store: dict[str, tuple[float, _T]] = {}

    def get(self, key: str) -> _T | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            self._store.pop(key, None)
            return None
        return value

    def put(self, key: str, value: _T) -> None:
        self._store[key] = (time.monotonic() + self._ttl, value)


class HseHttpPersonsGateway:
    """Best-effort gateway over hse.ru/org/persons (implements IHsePersonsGateway)."""

    def __init__(
        self,
        *,
        base_url: str,
        list_path: str,
        campus_udept: dict[str, str],
        user_agent: str,
        request_timeout_s: float,
        min_request_interval_s: float,
        max_concurrency: int,
        retries: int,
        list_cache_ttl_s: float,
        detail_cache_ttl_s: float,
        facets_cache_ttl_s: float,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._list_path = list_path
        self._campus_udept = campus_udept
        self._headers = {"User-Agent": user_agent}
        self._timeout = request_timeout_s
        self._min_interval = min_request_interval_s
        self._retries = retries

        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._gate_lock = asyncio.Lock()
        self._last_request_at = 0.0
        self._list_cache: _TTLCache[HseSearchResult] = _TTLCache(list_cache_ttl_s)
        self._detail_cache: _TTLCache[HsePersonDetail] = _TTLCache(detail_cache_ttl_s)
        self._facets_cache: _TTLCache[HseFacets] = _TTLCache(facets_cache_ttl_s)

    # ── outbound request with the politeness layer ────────────────────────────
    async def _throttle(self) -> None:
        async with self._gate_lock:
            wait = self._min_interval - (time.monotonic() - self._last_request_at)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_at = time.monotonic()

    async def _get(self, url: str) -> str | None:
        async with self._semaphore:
            for attempt in range(self._retries + 1):
                await self._throttle()
                try:
                    async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
                        resp = await client.get(url, headers=self._headers)
                except httpx.HTTPError as exc:
                    logger.warning("hse persons request failed", url=url, error_type=type(exc).__name__)
                    if attempt < self._retries:
                        await asyncio.sleep(min(self._min_interval * (2**attempt), 30.0))
                        continue
                    return None
                if resp.status_code == 429 or resp.status_code >= 500:
                    if attempt < self._retries:
                        retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
                        await asyncio.sleep(
                            retry_after if retry_after is not None else self._min_interval * (2**attempt)
                        )
                        continue
                    logger.warning("hse persons request rejected", url=url, status=resp.status_code)
                    return None
                if resp.status_code != 200:
                    return None
                return resp.text
        return None

    # ── query URL building ────────────────────────────────────────────────────
    def _effective_udept(self, query: HsePersonQuery) -> str:
        if query.udept:
            return query.udept
        return self._campus_udept.get(query.campus, "")

    def _resolve_ltr(self, query: HsePersonQuery) -> str:
        if query.ltr:
            return query.ltr
        m = _LETTER_RE.search(query.name)
        if not m:
            return ""
        letter = m.group(0).upper()
        return "Е" if letter == "Ё" else letter

    def _build_list_url(self, ltr: str, udept: str, query: HsePersonQuery) -> str | None:
        # HSE joins facets with ';' (e.g. ?ltr=%D0%98;udept=135083;position=5).
        facets = (
            ("ltr", quote(ltr) if ltr else ""),
            ("udept", udept),
            ("category", query.category),
            ("scirank", query.scirank),
            ("position", query.position),
            ("intst", query.intst),
        )
        parts = [f"{key}={value}" for key, value in facets if value]
        if not parts:
            # No narrowing at all — refuse rather than pull the whole default page.
            return None
        return f"{self._base_url}{self._list_path}?" + ";".join(parts)

    # ── gateway API ───────────────────────────────────────────────────────────
    async def search(self, query: HsePersonQuery) -> HseSearchResult:
        ltr = self._resolve_ltr(query)
        udept = self._effective_udept(query)
        url = self._build_list_url(ltr, udept, query)
        if url is None:
            return HseSearchResult()

        cached = self._list_cache.get(url)
        if cached is not None:
            return _apply_name_filter(cached, query)

        html = await self._get(url)
        if html is None:
            return HseSearchResult()
        result = HseSearchResult(
            persons=tuple(parser.parse_cards(html)),
            interests=parser.parse_interests(html, _MAX_INTEREST_CHIPS),
        )
        self._list_cache.put(url, result)
        return _apply_name_filter(result, query)

    async def get_detail(self, person_id: str) -> HsePersonDetail | None:
        pid = person_id.strip()
        if not pid.isdigit():
            return None
        cached = self._detail_cache.get(pid)
        if cached is not None:
            return cached
        html = await self._get(f"{self._base_url}/org/persons/{pid}")
        if html is None:
            return None
        detail = parser.parse_profile(html, pid)
        self._detail_cache.put(pid, detail)
        return detail

    async def get_facets(self, campus: str) -> HseFacets:
        udept = self._campus_udept.get(campus, "")
        cached = self._facets_cache.get(campus)
        if cached is not None:
            return cached
        url = f"{self._base_url}{self._list_path}" + (f"?udept={udept}" if udept else "")
        html = await self._get(url)
        if html is None:
            return HseFacets()
        facets = parser.parse_facets(html)
        self._facets_cache.put(campus, facets)
        return facets


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _apply_name_filter(result: HseSearchResult, query: HsePersonQuery) -> HseSearchResult:
    persons = result.persons
    name = query.name.strip()
    if name:
        needle = _normalize(name)
        persons = tuple(p for p in persons if needle in _normalize(p.full_name))
    limit = max(1, query.limit)
    return HseSearchResult(persons=persons[:limit], interests=result.interests)
