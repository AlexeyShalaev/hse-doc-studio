"""Политика исходящих запросов: разрешение имени, проверка каждого адреса, закрепление IP."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Iterable

from hse_doc_studio.core.egress import (
    EgressAllowlist,
    EgressPurpose,
    EgressTarget,
    check_address,
    check_host_name,
)

Resolver = Callable[[str, int], Awaitable[list[str]]]

_DEFAULT_PORT = 443


async def system_resolver(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


class ResolvingEgressPolicy:
    """Каждый адрес ответа DNS обязан пройти правила: смесь публичного и внутреннего адреса отвергается."""

    def __init__(self, allowlist: Iterable[str] = (), resolver: Resolver = system_resolver) -> None:
        self._allowlist = EgressAllowlist.parse(allowlist)
        self._resolver = resolver

    async def authorize(
        self, host: str, port: int | None = None, *, purpose: EgressPurpose = EgressPurpose.user
    ) -> EgressTarget:
        check_host_name(host)
        literal = host.strip("[]")
        try:
            ipaddress.ip_address(literal)
        except ValueError:
            addresses = await self._resolver(host, port or _DEFAULT_PORT)
        else:
            addresses = [literal]
        if not addresses:
            raise socket.gaierror(socket.EAI_NONAME, "no addresses")
        for address in addresses:
            check_address(host, ipaddress.ip_address(address.split("%", 1)[0]), purpose, self._allowlist)
        return EgressTarget(host, port, tuple(addresses))


class AllowAllEgressPolicy:
    """Режим local: человек ходит со своей машины в свою сеть, ограничивать нечего."""

    async def authorize(
        self, host: str, port: int | None = None, *, purpose: EgressPurpose = EgressPurpose.user
    ) -> EgressTarget:
        return EgressTarget(host, port, ())
