"""Ограничение админки по хосту и IP клиента (HSE_STUDIO__ADMIN__*).

Пустые списки не ограничивают ничего. Если заданы оба, нужно пройти оба: заголовок Host подделывает любой
клиент, поэтому только по хосту админку не закрыть, а сетевой диапазон без хоста не привязывает её к адресу сайта.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from dataclasses import dataclass

type Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def _host_only(raw: str) -> str:
    """Имя узла без порта и точки на конце, в нижнем регистре; IPv6 приходит в квадратных скобках."""
    value = raw.strip().lower()
    if value.startswith("["):
        return value[1 : value.find("]")] if "]" in value else value[1:]
    if value.count(":") == 1:
        value = value.split(":", 1)[0]
    return value.rstrip(".")


def _host_matches(pattern: str, host: str) -> bool:
    if pattern.startswith("*."):
        return host.endswith(pattern[1:]) and host != pattern[2:]
    return host == pattern


@dataclass(frozen=True)
class AdminAccessPolicy:
    hosts: tuple[str, ...] = ()
    networks: tuple[Network, ...] = ()

    @classmethod
    def parse(cls, hosts: Iterable[str], cidrs: Iterable[str]) -> AdminAccessPolicy:
        """Разбирает списки из настроек; неверная запись даёт ValueError, чтобы опечатка не открывала админку."""
        parsed_hosts = tuple(h for h in (_host_only(item) for item in hosts) if h)
        if any("/" in h or " " in h for h in parsed_hosts):
            msg = "admin allowed host must be a name like admin.example.org or *.example.org"
            raise ValueError(msg)
        networks = tuple(ipaddress.ip_network(item.strip(), strict=False) for item in cidrs if item.strip())
        return cls(hosts=parsed_hosts, networks=networks)

    @property
    def restricted(self) -> bool:
        return bool(self.hosts or self.networks)

    def allows(self, host: str | None, ip: str | None) -> bool:
        if self.hosts and not (host and any(_host_matches(p, _host_only(host)) for p in self.hosts)):
            return False
        if not self.networks:
            return True
        try:
            address = ipaddress.ip_address((ip or "").strip())
        except ValueError:
            return False
        return any(address in net for net in self.networks)
