from __future__ import annotations

import socket

import pytest
from hse_doc_studio.core.egress import EgressBlockedError, EgressPurpose
from hse_doc_studio.infra.egress.policy import AllowAllEgressPolicy, ResolvingEgressPolicy


def _resolver(table: dict[str, list[str]]):  # type: ignore[no-untyped-def]
    async def resolve(host: str, port: int) -> list[str]:
        if host not in table:
            raise socket.gaierror(socket.EAI_NONAME, "unknown")
        return table[host]

    return resolve


async def test__authorize__public_name__returns_pinned_addresses() -> None:
    policy = ResolvingEgressPolicy(resolver=_resolver({"git.example.org": ["93.184.216.34"]}))

    target = await policy.authorize("git.example.org", 443)

    assert target.addresses == ("93.184.216.34",)


@pytest.mark.parametrize("host", ["127.0.0.1", "169.254.169.254", "[::1]", "10.0.0.1", "0x7f.1"])
async def test__authorize__literal_internal_address__blocked(host: str) -> None:
    policy = ResolvingEgressPolicy(resolver=_resolver({"0x7f.1": ["127.0.0.1"]}))

    with pytest.raises(EgressBlockedError):
        await policy.authorize(host, 80)


async def test__authorize__name_resolving_to_internal__blocked() -> None:
    policy = ResolvingEgressPolicy(resolver=_resolver({"sneaky.example": ["127.0.0.1"]}))

    with pytest.raises(EgressBlockedError):
        await policy.authorize("sneaky.example")


async def test__authorize__mixed_answer__blocked_when_any_address_is_internal() -> None:
    policy = ResolvingEgressPolicy(resolver=_resolver({"rebind.example": ["93.184.216.34", "10.0.0.7"]}))

    with pytest.raises(EgressBlockedError):
        await policy.authorize("rebind.example")


async def test__authorize__metadata_hostname__blocked_before_dns() -> None:
    policy = ResolvingEgressPolicy(resolver=_resolver({}))

    with pytest.raises(EgressBlockedError):
        await policy.authorize("metadata.google.internal")


async def test__authorize__unresolvable_name__oserror_not_policy_error() -> None:
    policy = ResolvingEgressPolicy(resolver=_resolver({}))

    with pytest.raises(OSError):  # noqa: PT011
        await policy.authorize("nope.example")


async def test__authorize__allowlist__lets_user_reach_listed_lan_host() -> None:
    policy = ResolvingEgressPolicy(["git.corp.local"], resolver=_resolver({"git.corp.local": ["10.1.1.1"]}))

    target = await policy.authorize("git.corp.local", 443)

    assert target.addresses == ("10.1.1.1",)


async def test__authorize__admin_purpose__lets_lan_through() -> None:
    policy = ResolvingEgressPolicy(resolver=_resolver({"ollama.lan": ["192.168.1.5"]}))

    target = await policy.authorize("ollama.lan", 11434, purpose=EgressPurpose.admin)

    assert target.addresses == ("192.168.1.5",)


async def test__allow_all__never_blocks() -> None:
    target = await AllowAllEgressPolicy().authorize("127.0.0.1", 80)

    assert target.addresses == ()
