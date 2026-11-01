"""Адрес клиента за обратными прокси.

``X-Forwarded-For`` учитывается только от доверенных прокси (``settings.auth.trusted_proxies``): иначе клиент
подставит любой адрес и обойдёт rate limit и ограничение админки по IP.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from functools import lru_cache

from fastapi import Request

type Network = ipaddress.IPv4Network | ipaddress.IPv6Network


@lru_cache(maxsize=16)
def parse_networks(entries: tuple[str, ...]) -> tuple[Network, ...]:
    return tuple(ipaddress.ip_network(entry.strip(), strict=False) for entry in entries if entry.strip())


def _parse_ip(raw: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(raw.strip())
    except ValueError:
        return None


def _trusted(raw: str, networks: Iterable[Network]) -> bool:
    ip = _parse_ip(raw)
    return ip is not None and any(ip in net for net in networks)


def resolve_client_ip(peer: str | None, forwarded_for: str | None, trusted_proxies: Iterable[str]) -> str:
    """Первый недоверенный адрес справа в цепочке; без доверенного пира заголовок игнорируется."""
    networks = parse_networks(tuple(trusted_proxies))
    peer = peer or ""
    if not forwarded_for or not _trusted(peer, networks):
        return peer
    hops = [hop.strip() for hop in forwarded_for.split(",") if hop.strip()]
    for hop in reversed(hops):
        if _parse_ip(hop) is None:
            return peer
        if not _trusted(hop, networks):
            return hop
    return hops[0] if hops else peer


def client_ip(request: Request, trusted_proxies: Iterable[str] | None = None) -> str:
    if trusted_proxies is None:
        from hse_doc_studio.api.config import settings  # noqa: PLC0415 — отложено: настройки тестируются подменой

        trusted_proxies = settings.auth.trusted_proxies
    peer = request.client.host if request.client else None
    return resolve_client_ip(peer, request.headers.get("x-forwarded-for"), trusted_proxies)
