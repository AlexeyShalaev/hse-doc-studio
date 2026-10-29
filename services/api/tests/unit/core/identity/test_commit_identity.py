from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from hse_doc_studio.core.identity.commit_identity import (
    DEFAULT_NOREPLY_DOMAIN,
    commit_identity,
    noreply_domain,
    noreply_email,
)
from hse_doc_studio.core.identity.entities import User, UserStatus

_USER = User(
    id="u_1",
    email="Ann@Example.org",
    email_normalized="ann@example.org",
    name="Ann Ivanova",
    status=UserStatus.active,
    created_at=datetime(2026, 10, 28, tzinfo=UTC),
)


@pytest.mark.parametrize(
    ("public_url", "expected"),
    [
        ("https://studio.example.org", "noreply.studio.example.org"),
        ("https://studio.example.org:8443/base", "noreply.studio.example.org"),
        ("http://localhost:8100", "noreply.localhost"),
        (None, DEFAULT_NOREPLY_DOMAIN),
        ("", DEFAULT_NOREPLY_DOMAIN),
        ("not a url", DEFAULT_NOREPLY_DOMAIN),
    ],
)
def test_noreply_domain_comes_from_public_url_host(public_url: str | None, expected: str) -> None:
    assert noreply_domain(public_url) == expected


def test_default_identity_hides_the_account_email() -> None:
    identity = commit_identity(_USER, "noreply.studio.example.org")

    assert (identity.name, identity.email, identity.is_noreply) == (
        "Ann Ivanova",
        noreply_email("u_1", "noreply.studio.example.org"),
        True,
    )


def test_account_email_is_used_only_on_opt_in() -> None:
    identity = commit_identity(replace(_USER, commit_use_account_email=True), "noreply.x")

    assert (identity.email, identity.is_noreply) == ("Ann@Example.org", False)


def test_own_commit_email_beats_the_opt_in_and_own_name_beats_the_account_name() -> None:
    user = replace(_USER, commit_name="A. Ivanova", commit_email="a@home.example", commit_use_account_email=True)

    identity = commit_identity(user, "noreply.x")

    assert (identity.name, identity.email, identity.is_noreply) == ("A. Ivanova", "a@home.example", False)
