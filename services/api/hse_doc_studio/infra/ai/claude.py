from __future__ import annotations

import ssl

import anthropic
import httpx

# Foundation for the AI-agents story: today this client only enumerates models
# (which also validates the key + endpoint). Streaming/dispatch will be added
# here later without changing the use-case or API surface.
_DEFAULT_CONNECT_TIMEOUT_S = 10.0
_DEFAULT_REQUEST_TIMEOUT_S = 60.0


def _verify_arg(ssl_verify: bool) -> bool | ssl.SSLContext:
    # When verifying, use the OS/system trust store (respects corporate or
    # self-signed CAs) rather than certifi's bundle. False disables verification.
    return ssl.create_default_context() if ssl_verify else False


class ClaudeClient:
    """Thin wrapper over the Anthropic SDK (async).

    Single-use: a fresh httpx client is built per instance and closed by
    ``list_models()``.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        ssl_verify: bool = True,
        connect_timeout_s: float = _DEFAULT_CONNECT_TIMEOUT_S,
        request_timeout_s: float = _DEFAULT_REQUEST_TIMEOUT_S,
    ) -> None:
        # Pass the timeout to BOTH the SDK (governs per-request) and the httpx
        # client (governs the connect/TLS handshake). base_url=None → default host.
        timeout = httpx.Timeout(request_timeout_s, connect=connect_timeout_s)
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            http_client=httpx.AsyncClient(verify=_verify_arg(ssl_verify), timeout=timeout),
        )

    async def list_models(self) -> list[str]:
        try:
            page = await self._client.models.list()
            return sorted(m.id for m in page.data)
        finally:
            await self._client.close()
