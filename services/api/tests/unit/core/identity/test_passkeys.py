from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hse_doc_studio.core.identity.entities import Session
from hse_doc_studio.core.identity.passkeys import (
    RelyingParty,
    RelyingPartyIssue,
    clean_passkey_name,
    resolve_relying_party,
    user_handle_of,
)

T0 = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("origin", "rp_id", "expected"),
    [
        ("https://studio.example.org", None, RelyingParty("studio.example.org", "S", "https://studio.example.org")),
        (
            "https://Studio.Example.org:8443",
            None,
            RelyingParty("studio.example.org", "S", "https://studio.example.org:8443"),
        ),
        ("http://localhost:8100", None, RelyingParty("localhost", "S", "http://localhost:8100")),
        ("http://studio.localhost", None, RelyingParty("studio.localhost", "S", "http://studio.localhost")),
        ("https://studio.example.org", "example.org", RelyingParty("example.org", "S", "https://studio.example.org")),
        (
            "https://studio.example.org",
            "Studio.Example.Org.",
            RelyingParty("studio.example.org", "S", "https://studio.example.org"),
        ),
    ],
    ids=["https", "port_and_case", "localhost_http", "dot_localhost", "parent_domain", "rp_id_normalized"],
)
def test__resolve_relying_party__usable_address__party(origin: str, rp_id: str | None, expected: RelyingParty) -> None:
    resolved = resolve_relying_party(origin, rp_id=rp_id, name="S")

    assert resolved.party == expected
    assert resolved.issue is None


@pytest.mark.parametrize(
    ("origin", "rp_id", "issue"),
    [
        (None, None, RelyingPartyIssue.no_address),
        ("not a url", None, RelyingPartyIssue.no_address),
        ("http://studio.example.org", None, RelyingPartyIssue.insecure_origin),
        ("https://10.0.0.5", None, RelyingPartyIssue.ip_address),
        ("http://127.0.0.1:8000", None, RelyingPartyIssue.ip_address),
        ("https://[::1]:8000", None, RelyingPartyIssue.ip_address),
        ("https://studio.example.org", "other.org", RelyingPartyIssue.rp_id_mismatch),
        ("https://studio.example.org", "ample.org", RelyingPartyIssue.rp_id_mismatch),
    ],
    ids=["none", "garbage", "plain_http", "ipv4", "loopback_ip", "ipv6", "foreign_rp_id", "suffix_not_label"],
)
def test__resolve_relying_party__unusable_address__issue(
    origin: str | None, rp_id: str | None, issue: RelyingPartyIssue
) -> None:
    resolved = resolve_relying_party(origin, rp_id=rp_id, name="S")

    assert resolved.party is None
    assert resolved.issue is issue


def test__user_handle_of__is_account_id_bytes_capped_at_64() -> None:
    assert user_handle_of("0f8e2c1a") == b"0f8e2c1a"
    assert len(user_handle_of("x" * 100)) == 64


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("  MacBook   Анны ", "MacBook Анны"), ("", "Passkey"), (None, "Passkey"), ("я" * 80, "я" * 64)],
)
def test__clean_passkey_name(raw: str | None, expected: str) -> None:
    assert clean_passkey_name(raw, "Passkey") == expected


def test__session_authenticated_at__latest_of_login_and_reauth() -> None:
    session = Session(
        id_hash="h", user_id="u", csrf_token="c", created_at=T0, last_seen_at=T0, expires_at=T0 + timedelta(days=1)
    )
    assert session.authenticated_at == T0
    later = T0 + timedelta(hours=2)
    assert Session(**{**session.__dict__, "reauth_at": later}).authenticated_at == later
