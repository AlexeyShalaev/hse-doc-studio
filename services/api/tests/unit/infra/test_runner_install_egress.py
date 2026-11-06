"""Политика адресов SSH-установки: частные сети и кластер закрыты без явной записи, метаданные облака закрыты всегда."""

from __future__ import annotations

import pytest
from hse_doc_studio.core.egress import EgressBlockedError, EgressBlockReason, EgressPurpose
from hse_doc_studio.infra.egress.policy import ResolvingEgressPolicy

pytestmark = pytest.mark.unit

_DNS = {
    "public.example.org": ["93.184.216.34"],
    "lan.corp.example": ["192.168.1.20"],
    "svc.cluster.local": ["10.96.0.1"],
    "rebind.example.org": ["93.184.216.34", "10.0.0.7"],
    "meta.example.org": ["169.254.169.254"],
}


async def _resolver(host: str, port: int) -> list[str]:
    if host not in _DNS:
        raise OSError("unresolved")
    return _DNS[host]


def _policy(*allow: str) -> ResolvingEgressPolicy:
    return ResolvingEgressPolicy(allow, resolver=_resolver)


async def _reason(policy: ResolvingEgressPolicy, host: str) -> EgressBlockReason | None:
    try:
        await policy.authorize(host, 22, purpose=EgressPurpose.user)
    except EgressBlockedError as exc:
        return exc.reason
    return None


@pytest.mark.parametrize(
    ("host", "reason"),
    [
        ("127.0.0.1", EgressBlockReason.loopback),
        ("10.96.0.1", EgressBlockReason.private),
        ("172.16.0.5", EgressBlockReason.private),
        ("192.168.1.20", EgressBlockReason.private),
        ("169.254.169.254", EgressBlockReason.metadata),
        ("169.254.10.10", EgressBlockReason.link_local),
        ("100.100.100.200", EgressBlockReason.metadata),
        ("fd00:ec2::254", EgressBlockReason.metadata),
        ("::1", EgressBlockReason.loopback),
        ("::ffff:127.0.0.1", EgressBlockReason.loopback),
        ("svc.cluster.local", EgressBlockReason.private),
        ("meta.example.org", EgressBlockReason.metadata),
        ("rebind.example.org", EgressBlockReason.private),
        ("0.0.0.0", EgressBlockReason.unspecified),  # noqa: S104
    ],
)
async def test__default_policy__blocks_internal_and_metadata(host: str, reason: EgressBlockReason) -> None:
    assert await _reason(_policy(), host) is reason


async def test__default_policy__lets_public_hosts_through_pinned_to_resolved_addresses() -> None:
    target = await _policy().authorize("public.example.org", 22, purpose=EgressPurpose.user)

    assert target.addresses == ("93.184.216.34",)


async def test__allowlist__opens_only_the_listed_internal_network() -> None:
    policy = _policy("192.168.1.0/24", "*.corp.example")

    assert await _reason(policy, "192.168.1.20") is None
    assert await _reason(policy, "lan.corp.example") is None
    assert await _reason(policy, "10.96.0.1") is EgressBlockReason.private
    assert await _reason(policy, "svc.cluster.local") is EgressBlockReason.private


async def test__allowlist__never_opens_cloud_metadata_or_link_local() -> None:
    policy = _policy("169.254.0.0/16", "meta.example.org", "169.254.169.254")

    assert await _reason(policy, "169.254.169.254") is EgressBlockReason.metadata
    assert await _reason(policy, "meta.example.org") is EgressBlockReason.metadata
    assert await _reason(policy, "169.254.10.10") is EgressBlockReason.link_local


async def test__unresolved_name_is_an_os_error_not_a_pass() -> None:
    with pytest.raises(OSError, match="unresolved"):
        await _policy().authorize("nope.example.org", 22, purpose=EgressPurpose.user)
