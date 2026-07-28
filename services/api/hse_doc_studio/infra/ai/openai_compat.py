from __future__ import annotations

import ssl

import httpx
import openai

# Covers both the plain `openai` provider type (base_url=None → api.openai.com)
# and `openai_compat` (any OpenAI-compatible endpoint: Ollama, vLLM, LM Studio,
# OpenRouter, …). Today only model enumeration is used; dispatch lands here later.
_DEFAULT_CONNECT_TIMEOUT_S = 10.0
_DEFAULT_REQUEST_TIMEOUT_S = 60.0


def _verify_arg(ssl_verify: bool) -> bool | ssl.SSLContext:
    # When verifying, use the OS/system trust store (respects corporate or
    # self-signed CAs) rather than certifi's bundle. False disables verification.
    return ssl.create_default_context() if ssl_verify else False


class OpenAICompatClient:
    """Thin wrapper over the OpenAI SDK (async), base_url-aware.

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
        # client (governs the connect/TLS handshake).
        timeout = httpx.Timeout(request_timeout_s, connect=connect_timeout_s)
        self._client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url or None,
            timeout=timeout,
            http_client=httpx.AsyncClient(verify=_verify_arg(ssl_verify), timeout=timeout),
        )

    async def list_models(self) -> list[str]:
        try:
            page = await self._client.models.list()
            return sorted(m.id for m in page.data)
        finally:
            await self._client.close()
