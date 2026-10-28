"""Клиент httpx, который ходит только по адресам, прошедшим политику.

Проверка стоит на подключении, а не перед запросом: имя разрешается один раз, подключение идёт к
проверенному IP (DNS rebinding не подменит адрес между проверкой и соединением), а каждый редирект
открывает новое соединение и проверяется заново. TLS и заголовок Host остаются за исходным именем.
Прокси из окружения не используются: через них проверку делал бы уже прокси.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import httpcore
import httpx
from httpcore import SOCKET_OPTION, AsyncNetworkBackend, AsyncNetworkStream

from hse_doc_studio.core.egress import EgressPurpose, IEgressPolicy


class PinningBackend(AsyncNetworkBackend):
    def __init__(self, policy: IEgressPolicy, purpose: EgressPurpose, inner: AsyncNetworkBackend | None = None) -> None:
        self._policy = policy
        self._purpose = purpose
        self._inner = inner or httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[SOCKET_OPTION] | None = None,
    ) -> AsyncNetworkStream:
        target = await self._policy.authorize(host, port, purpose=self._purpose)
        if not target.addresses:
            return await self._inner.connect_tcp(host, port, timeout, local_address, socket_options)
        last: Exception | None = None
        for address in target.addresses:
            try:
                return await self._inner.connect_tcp(address, port, timeout, local_address, socket_options)
            except httpcore.ConnectError as exc:
                last = exc
        assert last is not None  # noqa: S101 — адреса не пусты
        raise last

    async def connect_unix_socket(
        self, path: str, timeout: float | None = None, socket_options: Iterable[SOCKET_OPTION] | None = None
    ) -> AsyncNetworkStream:
        raise httpcore.ConnectError("unix sockets are not allowed")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


def egress_transport(
    policy: IEgressPolicy,
    purpose: EgressPurpose = EgressPurpose.user,
    *,
    verify: Any = True,
    backend: AsyncNetworkBackend | None = None,
) -> httpx.AsyncHTTPTransport:
    transport = httpx.AsyncHTTPTransport(verify=verify, trust_env=False)
    pool = transport._pool  # noqa: SLF001 — httpx не принимает сетевой бэкенд, подменяем его в пуле
    pool._network_backend = PinningBackend(policy, purpose, backend)  # noqa: SLF001
    return transport


def egress_client(
    policy: IEgressPolicy,
    purpose: EgressPurpose = EgressPurpose.user,
    *,
    verify: Any = True,
    backend: AsyncNetworkBackend | None = None,
    **kwargs: Any,
) -> httpx.AsyncClient:
    """AsyncClient с проверкой адресов. Остальные параметры (timeout, headers, follow_redirects) как у httpx."""
    return httpx.AsyncClient(transport=egress_transport(policy, purpose, verify=verify, backend=backend), **kwargs)
