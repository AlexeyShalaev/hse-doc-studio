from __future__ import annotations

import pytest
from hse_doc_studio.core.identity.admin_access import AdminAccessPolicy


def test__policy__empty__allows_everyone() -> None:
    policy = AdminAccessPolicy.parse([], [])

    assert not policy.restricted
    assert policy.allows(None, None)
    assert policy.allows("any.example.org", "203.0.113.5")


@pytest.mark.parametrize(
    ("host", "allowed"),
    [
        ("admin.example.org", True),
        ("ADMIN.Example.org:8443", True),
        ("admin.example.org.", True),
        ("other.example.org", False),
        ("sub.admin.example.org", False),
        (None, False),
    ],
)
def test__policy__hosts__exact_name_without_port_and_case(host: str | None, allowed: bool) -> None:
    policy = AdminAccessPolicy.parse(["admin.example.org"], [])

    assert policy.allows(host, "203.0.113.5") is allowed


def test__policy__wildcard_host__matches_subdomains_only() -> None:
    policy = AdminAccessPolicy.parse(["*.corp.local"], [])

    assert policy.allows("admin.corp.local", None)
    assert policy.allows("a.b.corp.local", None)
    assert not policy.allows("corp.local", None)
    assert not policy.allows("evilcorp.local", None)


@pytest.mark.parametrize(
    ("ip", "allowed"),
    [
        ("10.1.2.3", True),
        ("127.0.0.1", True),
        ("::1", False),
        ("192.168.1.1", False),
        ("", False),
        (None, False),
        ("x", False),
    ],
)
def test__policy__cidrs__by_client_ip(ip: str | None, allowed: bool) -> None:
    policy = AdminAccessPolicy.parse([], ["10.0.0.0/8", "127.0.0.1"])

    assert policy.restricted
    assert policy.allows("any", ip) is allowed


def test__policy__both_lists__both_must_pass() -> None:
    policy = AdminAccessPolicy.parse(["admin.example.org"], ["10.0.0.0/8"])

    assert policy.allows("admin.example.org", "10.0.0.7")
    assert not policy.allows("admin.example.org", "8.8.8.8")
    assert not policy.allows("evil.example.org", "10.0.0.7")


def test__policy__ipv6_host_and_network() -> None:
    policy = AdminAccessPolicy.parse(["[::1]:8000"], ["::1/128"])

    assert policy.allows("[::1]:8000", "::1")


@pytest.mark.parametrize(("hosts", "cidrs"), [(["10.0.0.0/8"], []), ([], ["not-an-ip"]), (["a b"], [])])
def test__policy__bad_entry__fails_instead_of_opening(hosts: list[str], cidrs: list[str]) -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        AdminAccessPolicy.parse(hosts, cidrs)
