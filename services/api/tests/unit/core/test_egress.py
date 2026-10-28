from __future__ import annotations

import ipaddress

import pytest
from hse_doc_studio.api.config import EgressConfig
from hse_doc_studio.core.egress import (
    EgressAllowlist,
    EgressBlockedError,
    EgressBlockReason,
    EgressPurpose,
    check_address,
    check_host_name,
    classify_address,
)


def _ip(raw: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    return ipaddress.ip_address(raw)


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("127.0.0.1", EgressBlockReason.loopback),
        ("::1", EgressBlockReason.loopback),
        ("::ffff:127.0.0.1", EgressBlockReason.loopback),
        ("169.254.169.254", EgressBlockReason.metadata),
        ("::ffff:169.254.169.254", EgressBlockReason.metadata),
        ("fd00:ec2::254", EgressBlockReason.metadata),
        ("100.100.100.200", EgressBlockReason.metadata),
        ("169.254.10.1", EgressBlockReason.link_local),
        ("fe80::1", EgressBlockReason.link_local),
        ("10.0.0.5", EgressBlockReason.private),
        ("172.16.3.4", EgressBlockReason.private),
        ("192.168.1.1", EgressBlockReason.private),
        ("fc00::1", EgressBlockReason.private),
        ("100.64.0.1", EgressBlockReason.reserved),
        ("0.0.0.0", EgressBlockReason.unspecified),
        ("224.0.0.1", EgressBlockReason.multicast),
        ("2002:7f00:1::1", EgressBlockReason.loopback),
        ("93.184.216.34", None),
        ("2606:4700:4700::1111", None),
    ],
)
def test__classify_address(raw: str, reason: EgressBlockReason | None) -> None:
    assert classify_address(_ip(raw)) is reason


def test__user_purpose__blocks_internal_and_passes_public() -> None:
    allowlist = EgressAllowlist()
    check_address("example.org", _ip("93.184.216.34"), EgressPurpose.user, allowlist)
    for raw in ("127.0.0.1", "10.1.2.3", "169.254.169.254"):
        with pytest.raises(EgressBlockedError):
            check_address(raw, _ip(raw), EgressPurpose.user, allowlist)


def test__admin_purpose__allows_lan_and_loopback_but_never_metadata() -> None:
    allowlist = EgressAllowlist()
    check_address("ollama.lan", _ip("192.168.1.20"), EgressPurpose.admin, allowlist)
    check_address("localhost", _ip("127.0.0.1"), EgressPurpose.admin, allowlist)
    for raw in ("169.254.169.254", "169.254.1.1", "0.0.0.0", "224.0.0.1"):  # noqa: S104
        with pytest.raises(EgressBlockedError):
            check_address(raw, _ip(raw), EgressPurpose.admin, allowlist)


def test__allowlist__opens_listed_internal_hosts_for_users() -> None:
    allowlist = EgressAllowlist.parse(["git.corp.local", "*.dev.corp", "10.20.0.0/16", "172.16.0.9"])
    check_address("git.corp.local", _ip("10.99.0.1"), EgressPurpose.user, allowlist)
    check_address("x.dev.corp", _ip("10.99.0.1"), EgressPurpose.user, allowlist)
    check_address("10.20.3.4", _ip("10.20.3.4"), EgressPurpose.user, allowlist)
    check_address("172.16.0.9", _ip("172.16.0.9"), EgressPurpose.user, allowlist)
    with pytest.raises(EgressBlockedError):
        check_address("evil.example", _ip("10.99.0.1"), EgressPurpose.user, allowlist)
    with pytest.raises(EgressBlockedError):
        check_address("172.16.0.10", _ip("172.16.0.10"), EgressPurpose.user, allowlist)


def test__allowlist__cannot_open_metadata_or_link_local() -> None:
    allowlist = EgressAllowlist.parse(["169.254.0.0/16", "metadata.google.internal"])
    with pytest.raises(EgressBlockedError):
        check_address("169.254.169.254", _ip("169.254.169.254"), EgressPurpose.user, allowlist)
    with pytest.raises(EgressBlockedError):
        check_host_name("metadata.google.internal")


def test__allowlist__bad_entry_is_rejected() -> None:
    with pytest.raises(ValueError, match="allowlist"):
        EgressAllowlist.parse(["not a host"])


def test__egress_config__rejects_a_bad_allowlist_entry_at_startup() -> None:
    assert EgressConfig(allowlist=["git.corp.local", "10.0.0.0/8"]).allowlist == ["git.corp.local", "10.0.0.0/8"]
    with pytest.raises(ValueError, match="allowlist"):
        EgressConfig(allowlist=["bad entry"])
