"""Исходящие запросы по адресам пользователей: порт IEgressPolicy и правила SSRF-защиты.

Сервер ходит туда, куда указал человек (git-репозиторий, сервер git). Без ограничений адрес
`http://169.254.169.254/` или `http://127.0.0.1:5432/` превращает Студию в прокси во внутреннюю сеть.
Правила чистые, без ввода-вывода: имя разрешает infra, сюда приходят уже адреса.

Две строгости. `user`: любой адрес из пользовательского ввода, закрыто всё, что не публичный интернет.
`admin`: адрес задал администратор установки (Ollama в локальной сети), поэтому разрешены частные сети и
loopback. Ни для кого не открыты адреса метаданных облака, link-local, неопределённый и multicast.
Администратор может явно разрешить внутренний узел списком allowlist (имя, IP или CIDR), но только вне
адресов метаданных и link-local.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


class EgressPurpose(StrEnum):
    user = "user"
    admin = "admin"


class EgressBlockReason(StrEnum):
    loopback = "loopback"
    private = "private"
    link_local = "link_local"
    metadata = "metadata"
    unspecified = "unspecified"
    multicast = "multicast"
    reserved = "reserved"
    metadata_host = "metadata_host"


class EgressBlockedError(Exception):
    """Адрес не прошёл политику; `reason` для журнала, пользователю текст не раскрывает, что именно внутри."""

    def __init__(self, host: str, reason: EgressBlockReason) -> None:
        super().__init__(f"egress to {host} is blocked: {reason.value}")
        self.host = host
        self.reason = reason


@dataclass(frozen=True)
class EgressTarget:
    """Проверенный узел: к этим адресам (и только к ним) надо подключаться, имя повторно не разрешают."""

    host: str
    port: int | None
    addresses: tuple[str, ...]


class IEgressPolicy(Protocol):
    async def authorize(
        self, host: str, port: int | None = None, *, purpose: EgressPurpose = EgressPurpose.user
    ) -> EgressTarget:
        """Разрешить имя и проверить каждый адрес.

        EgressBlockedError, если хоть один закрыт; OSError, если имя не разрешилось.
        """
        ...


_METADATA_NETWORKS = tuple(
    ipaddress.ip_network(net)
    for net in (
        "169.254.169.254/32",
        "169.254.170.2/32",
        "100.100.100.200/32",
        "192.0.0.192/32",
        "fd00:ec2::254/128",
    )
)
_METADATA_HOSTS = frozenset({"metadata", "metadata.google.internal", "instance-data", "instance-data.ec2.internal"})


def normalize_address(address: IPAddress) -> IPAddress:
    """IPv4 внутри IPv6 (::ffff:127.0.0.1) проверяется как IPv4: иначе он обходит правила."""
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return address.ipv4_mapped
        if address.sixtofour is not None:
            return address.sixtofour
    return address


def classify_address(address: IPAddress) -> EgressBlockReason | None:
    """Почему адрес не публичный; None, если это обычный адрес интернета."""
    ip = normalize_address(address)
    if any(ip in net for net in _METADATA_NETWORKS if net.version == ip.version):
        return EgressBlockReason.metadata
    flags = (
        (ip.is_loopback, EgressBlockReason.loopback),
        (ip.is_link_local, EgressBlockReason.link_local),
        (ip.is_unspecified, EgressBlockReason.unspecified),
        (ip.is_multicast, EgressBlockReason.multicast),
        (ip.is_private, EgressBlockReason.private),
        (not ip.is_global, EgressBlockReason.reserved),
    )
    return next((reason for flag, reason in flags if flag), None)


# Эти причины нельзя снять ни режимом admin, ни allowlist.
_NEVER_ALLOWED = frozenset(
    {
        EgressBlockReason.metadata,
        EgressBlockReason.link_local,
        EgressBlockReason.unspecified,
        EgressBlockReason.multicast,
        EgressBlockReason.metadata_host,
    }
)
_ADMIN_ALLOWED = frozenset({EgressBlockReason.loopback, EgressBlockReason.private, EgressBlockReason.reserved})


@dataclass(frozen=True)
class EgressAllowlist:
    """Явное разрешение администратора: имена (`git.corp.local`, `*.corp.local`) и сети (`10.0.0.0/8`, `10.1.2.3`)."""

    hosts: frozenset[str] = frozenset()
    suffixes: tuple[str, ...] = ()
    networks: tuple[IPNetwork, ...] = ()

    @classmethod
    def parse(cls, entries: Iterable[str]) -> EgressAllowlist:
        hosts: set[str] = set()
        suffixes: list[str] = []
        networks: list[IPNetwork] = []
        for raw in entries:
            entry = raw.strip().lower()
            if not entry:
                continue
            try:
                networks.append(ipaddress.ip_network(entry, strict=False))
                continue
            except ValueError:
                pass
            if entry.startswith("*."):
                suffixes.append(entry[1:])
            elif "/" in entry or any(char.isspace() for char in entry) or ":" in entry:
                msg = f"некорректная запись allowlist: {raw!r}"
                raise ValueError(msg)
            else:
                hosts.add(entry.rstrip("."))
        return cls(frozenset(hosts), tuple(suffixes), tuple(networks))

    def allows(self, host: str, address: IPAddress) -> bool:
        name = host.lower().rstrip(".")
        if name in self.hosts or any(name.endswith(suffix) for suffix in self.suffixes):
            return True
        ip = normalize_address(address)
        return any(ip in net for net in self.networks if net.version == ip.version)


def check_host_name(host: str) -> None:
    """Имена метаданных закрыты по имени, даже если DNS у них отвечает чем-то публичным."""
    if host.lower().rstrip(".") in _METADATA_HOSTS:
        raise EgressBlockedError(host, EgressBlockReason.metadata_host)


def check_address(host: str, address: IPAddress, purpose: EgressPurpose, allowlist: EgressAllowlist) -> None:
    """Бросает EgressBlockedError, если к адресу нельзя подключаться."""
    reason = classify_address(address)
    if reason is None:
        return
    if reason in _NEVER_ALLOWED:
        raise EgressBlockedError(host, reason)
    if purpose is EgressPurpose.admin and reason in _ADMIN_ALLOWED:
        return
    if allowlist.allows(host, address):
        return
    raise EgressBlockedError(host, reason)
