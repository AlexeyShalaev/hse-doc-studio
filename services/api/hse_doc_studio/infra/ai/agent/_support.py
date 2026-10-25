from __future__ import annotations

import ssl

import httpx2

# Shared client-construction helpers for the agent adapters. Mirrors the
# per-instance HTTP setup in infra/ai/openai_compat.py and infra/ai/claude.py
# (system trust store when verifying; verification off for self-signed hosts).
# httpx2, not httpx: the Anthropic SDK 2.x rejects an `httpx` client outright,
# and the OpenAI SDK 3.x accepts both.


def verify_arg(ssl_verify: bool) -> bool | ssl.SSLContext:
    # When verifying, use the OS/system trust store (respects corporate or
    # self-signed CAs) rather than certifi's bundle. False disables verification.
    return ssl.create_default_context() if ssl_verify else False


def build_async_http_client(
    *,
    ssl_verify: bool,
    connect_timeout_s: float,
    request_timeout_s: float,
) -> httpx2.AsyncClient:
    # During streaming the read timeout is the max gap between received chunks,
    # not a wall-clock cap on the whole generation, so the provider's
    # request_timeout_s is a safe per-read bound.
    timeout = httpx2.Timeout(request_timeout_s, connect=connect_timeout_s)
    return httpx2.AsyncClient(verify=verify_arg(ssl_verify), timeout=timeout)
