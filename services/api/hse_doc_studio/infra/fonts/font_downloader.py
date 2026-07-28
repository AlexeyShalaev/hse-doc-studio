from __future__ import annotations

import httpx

from hse_doc_studio.core.fonts.repositories import IFontDownloader

# GitHub raw URLs redirect to a CDN host, so redirects must be followed.
_CONNECT_TIMEOUT_S = 30.0


class HttpxFontDownloader(IFontDownloader):
    """Downloads a single font file over HTTPS.

    Font files are small (<1 MB), so this fetches the whole body in one call
    rather than mirroring the SSE/streaming pattern used for multi-GB pulls.
    """

    def __init__(self, timeout_s: float) -> None:
        self._timeout_s = timeout_s

    async def download(self, url: str) -> bytes:
        timeout = httpx.Timeout(self._timeout_s, connect=_CONNECT_TIMEOUT_S)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content
