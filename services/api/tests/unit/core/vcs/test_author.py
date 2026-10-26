from __future__ import annotations

import pytest
from hse_doc_studio.core.vcs.author import MAX_EMAIL, MAX_NAME, normalize_email, normalize_name
from hse_doc_studio.core.vcs.errors import ProfileValidationError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Алексей Шалаев", "Алексей Шалаев"),
        ("  Alice   Ivanova  ", "Alice Ivanova"),
        ("Alice Ivanova", "Alice Ivanova"),
        ("Café", "Café"),
        ("Alice 🚀", "Alice 🚀"),
        ("A", "A"),
        ("N" * MAX_NAME, "N" * MAX_NAME),
        ("J. R. R.", "J. R. R."),
    ],
)
def test__normalize_name__valid__returns_clean_name(raw: str, expected: str) -> None:
    assert normalize_name(raw) == expected


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (None, "name_required"),
        ("", "name_required"),
        ("   ", "name_required"),
        ("N" * (MAX_NAME + 1), "name_too_long"),
        ("Eve <x>", "name_invalid"),
        ("Eve>", "name_invalid"),
        ("Eve\nEvil", "name_invalid"),
        ("Eve\tEvil", "name_invalid"),
        ("Eve\x00", "name_invalid"),
        ("Eve\x7f", "name_invalid"),
        (".", "name_invalid"),
        (" ,;:\"' ", "name_invalid"),
        ("...", "name_invalid"),
    ],
)
def test__normalize_name__invalid__raises_with_code(raw: str | None, code: str) -> None:
    with pytest.raises(ProfileValidationError) as exc:
        normalize_name(raw)

    assert exc.value.code == code
    assert exc.value.field == "name"
    assert exc.value.message


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("alice@example.org", "alice@example.org"),
        ("  Alice.Ivanova@Edu.HSE.ru ", "Alice.Ivanova@edu.hse.ru"),
        ("123456+alice@users.noreply.github.com", "123456+alice@users.noreply.github.com"),
        ("алиса@пример.рф", "алиса@пример.рф"),
    ],
)
def test__normalize_email__valid__lowercases_only_domain(raw: str, expected: str) -> None:
    assert normalize_email(raw) == expected


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (None, "email_required"),
        ("", "email_required"),
        ("a@" + "b" * MAX_EMAIL + ".org", "email_too_long"),
        ("not-an-email", "email_invalid"),
        ("alice@localhost", "email_invalid"),
        ("alice@example", "email_invalid"),
        ("alice@@example.org", "email_invalid"),
        ("alice@exa mple.org", "email_invalid"),
        ("a<v>e@example.org", "email_invalid"),
        ("alice@exa\nmple.org", "email_invalid"),
        ("alice@.example.org", "email_invalid"),
        ("alice@example..org", "email_invalid"),
        ("alice@example.org.", "email_invalid"),
        ("@example.org", "email_invalid"),
    ],
)
def test__normalize_email__invalid__raises_with_code(raw: str | None, code: str) -> None:
    with pytest.raises(ProfileValidationError) as exc:
        normalize_email(raw)

    assert exc.value.code == code
    assert exc.value.field == "email"


def test__normalize_email__without_dot_requirement__accepts_local_host() -> None:
    assert normalize_email("alice@localhost", require_domain_dot=False) == "alice@localhost"
    with pytest.raises(ProfileValidationError):
        normalize_email("not-an-email", require_domain_dot=False)
