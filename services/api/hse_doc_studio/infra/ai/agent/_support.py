from __future__ import annotations

import ssl

import httpx

# Shared client-construction helpers for the agent adapters. Mirrors the
# per-instance httpx setup in infra/ai/openai_compat.py and infra/ai/claude.py
# (system trust store when verifying; verification off for self-signed hosts).


def verify_arg(ssl_verify: bool) -> bool | ssl.SSLContext:
    # When verifying, use the OS/system trust store (respects corporate or
    # self-signed CAs) rather than certifi's bundle. False disables verification.
    return ssl.create_default_context() if ssl_verify else False


def build_async_http_client(
    *,
    ssl_verify: bool,
    connect_timeout_s: float,
    request_timeout_s: float,
) -> httpx.AsyncClient:
    # During streaming the read timeout is the max gap between received chunks,
    # not a wall-clock cap on the whole generation, so the provider's
    # request_timeout_s is a safe per-read bound.
    timeout = httpx.Timeout(request_timeout_s, connect=connect_timeout_s)
    return httpx.AsyncClient(verify=verify_arg(ssl_verify), timeout=timeout)
