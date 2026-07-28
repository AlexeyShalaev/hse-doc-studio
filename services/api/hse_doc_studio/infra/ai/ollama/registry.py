from __future__ import annotations

import html as html_lib
import re

import httpx
import structlog

from hse_doc_studio.core.entities import RegistryModel

logger = structlog.get_logger()

_MAX_RESULTS = 40
# ollama.com marks each result with stable `x-test-*` hooks (test attributes),
# which are far more durable than CSS classes — anchor the scrape on those.
_BLOCK_SPLIT = re.compile(r"<li x-test-model")
_NAME_RE = re.compile(r"x-test-search-response-title[^>]*>\s*([^<]+?)\s*<")
_DESC_RE = re.compile(r"<p[^>]*>\s*([^<]+?)\s*</p>", re.S)
_PULLS_RE = re.compile(r"x-test-pull-count[^>]*>\s*([^<]+?)\s*<")
_CAP_RE = re.compile(r"x-test-capability[^>]*>\s*([^<]+?)\s*<")


def _clean(text: str) -> str:
    return html_lib.unescape(re.sub(r"\s+", " ", text)).strip()


def _parse_search_html(html: str) -> list[RegistryModel]:
    out: list[RegistryModel] = []
    seen: set[str] = set()
    for block in _BLOCK_SPLIT.split(html)[1:]:
        name_m = _NAME_RE.search(block)
        if not name_m:
            continue
        name = name_m.group(1).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        desc_m = _DESC_RE.search(block)
        pulls_m = _PULLS_RE.search(block)
        out.append(
            RegistryModel(
                name=name,
                description=_clean(desc_m.group(1)) if desc_m else "",
                pulls=pulls_m.group(1).strip() if pulls_m else "",
                capabilities=[c.strip() for c in _CAP_RE.findall(block)],
            )
        )
    return out


class OllamaRegistryClient:
    """Best-effort search of the public Ollama registry (ollama.com/search).

    Ollama has no official search API, so this scrapes the server-rendered
    search page (anchored on stable ``x-test-*`` attributes). Like the Docker
    Hub tag listing it degrades gracefully — any error or layout change yields
    an empty list, never an exception, so discovery failing just hides the
    remote results while the curated catalog + custom pull keep working.
    """

    def __init__(self, search_url: str, timeout_s: float) -> None:
        self._search_url = search_url
        self._timeout_s = timeout_s

    async def search(self, query: str) -> list[RegistryModel]:
        q = query.strip()
        if not q:
            return []
        try:
            async with httpx.AsyncClient(timeout=self._timeout_s, follow_redirects=True) as client:
                resp = await client.get(
                    self._search_url,
                    params={"q": q},
                    headers={"User-Agent": "Mozilla/5.0 (compatible; hse-doc-studio)"},
                )
        except httpx.HTTPError as exc:
            logger.warning("ollama registry search failed", error_type=type(exc).__name__)
            return []
        if resp.status_code != 200:
            return []
        return _parse_search_html(resp.text)[:_MAX_RESULTS]
