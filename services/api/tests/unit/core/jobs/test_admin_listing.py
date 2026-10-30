"""Правила списков раннеров: сравнение версий по числам и статус токена регистрации."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hse_doc_studio.core.jobs.admin import RegistrationTokenStatus, registration_token_status, version_key
from hse_doc_studio.core.jobs.runners import RegistrationToken
from hse_doc_studio.infra.db.search import contains_pattern

NOW = datetime(2026, 10, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    ("older", "newer"),
    [
        ("0.9.9", "0.10.0"),
        ("0.10.0", "0.10.1"),
        ("0.2", "0.2.1"),
        ("", "0.0.1"),
        ("dev", "0.1.0"),
        ("1.2.3-rc1", "1.2.4"),
    ],
)
def test__version_key__numeric_not_lexical(older: str, newer: str) -> None:
    assert version_key(older) < version_key(newer)


def test__version_key__missing_parts_are_zero_and_suffix_ignored() -> None:
    assert version_key("0.2") == version_key("0.2.0") == (0, 2, 0, 0)
    assert version_key("1.2.3rc1") == (1, 2, 3, 0)


def _token(**kwargs: object) -> RegistrationToken:
    base: dict[str, object] = {
        "id": "t",
        "token_hash": "h",
        "created_by": None,
        "created_at": NOW,
        "expires_at": NOW + timedelta(hours=1),
        "max_uses": 2,
        "uses": 0,
    }
    return RegistrationToken(**{**base, **kwargs})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("token", "status"),
    [
        (_token(), RegistrationTokenStatus.active),
        (_token(expires_at=None), RegistrationTokenStatus.active),
        (_token(expires_at=NOW), RegistrationTokenStatus.expired),
        (_token(uses=2, expires_at=NOW - timedelta(days=1)), RegistrationTokenStatus.exhausted),
        (_token(uses=2, revoked_at=NOW), RegistrationTokenStatus.revoked),
    ],
)
def test__registration_token_status__precedence(token: RegistrationToken, status: RegistrationTokenStatus) -> None:
    assert registration_token_status(token, NOW) is status


@pytest.mark.parametrize(
    ("q", "pattern"),
    [("  Анна ", "%Анна%"), ("100%", "%100\\%%"), ("a_b", "%a\\_b%"), ("c:\\x", "%c:\\\\x%")],
)
def test__contains_pattern__escapes_like_wildcards(q: str, pattern: str) -> None:
    assert contains_pattern(q) == pattern
