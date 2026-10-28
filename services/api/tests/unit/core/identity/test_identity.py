from __future__ import annotations

import json
from pathlib import Path

import pytest
from hse_doc_studio.core.access.entities import Actor, ActorKind, ActorSource
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.core.identity.errors import MESSAGES, IdentityError, IdentityErrorCode, message_for
from hse_doc_studio.core.identity.normalize import (
    email_domain,
    hash_token,
    is_reserved_slug,
    is_valid_email,
    is_valid_slug,
    new_token,
    normalize_domain,
    normalize_email,
)
from hse_doc_studio.core.identity.passwords import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    check_password,
    common_passwords,
    password_problem,
)

_CODES = Path(__file__).resolve().parents[6] / "contracts" / "server" / "error_codes.json"


def test_email_is_casefolded_nfc_and_keeps_plus() -> None:
    assert normalize_email("  Ann+Tag@Example.COM ") == "ann+tag@example.com"
    assert normalize_email("é@x.ru") == normalize_email("é@x.ru")


def test_email_shape_and_domain() -> None:
    assert is_valid_email("a@b.co")
    assert not is_valid_email("a@b")
    assert not is_valid_email("a b@c.ru")
    assert not is_valid_email("a@" + "b" * 260 + ".ru")
    assert email_domain("Ann@Example.COM") == "example.com"
    assert normalize_domain(" @HSE.ru ") == "hse.ru"


@pytest.mark.parametrize("slug", ["a", "hse", "my-org", "a1", "x" * 40])
def test_slug_valid(slug: str) -> None:
    assert is_valid_slug(slug)


@pytest.mark.parametrize("slug", ["", "-a", "a-", "A", "a_b", "a b", "x" * 41, "орг"])
def test_slug_invalid(slug: str) -> None:
    assert not is_valid_slug(slug)


def test_reserved_slugs_are_valid_shape() -> None:
    assert is_reserved_slug("admin")
    assert not is_reserved_slug("hse")


def test_tokens_are_unique_and_hashed() -> None:
    a, b = new_token(), new_token()
    assert a != b
    assert len(hash_token(a)) == 64
    assert hash_token(a) == hash_token(a)
    assert hash_token(a) != a


def test_error_codes_match_contract() -> None:
    contract = set(json.loads(_CODES.read_text(encoding="utf-8")))
    # Закрытый список контракта и перечисление совпадают: достижимый код нельзя оставить без записи и текста
    assert contract == {c.value for c in IdentityErrorCode}


def test_every_code_has_ru_and_en() -> None:
    assert set(MESSAGES) == set(IdentityErrorCode)
    for code, (ru, en) in MESSAGES.items():
        assert ru.strip(), code
        assert en.strip(), code
        assert ru != en, code


def test_message_follows_interface_language() -> None:
    try:
        set_interface_language("en")
        assert IdentityError(IdentityErrorCode.auth_required).detail == "Sign in required."
        set_interface_language("ru")
        assert message_for(IdentityErrorCode.auth_required) == "Нужно войти."
    finally:
        set_interface_language(None)


def test_password_length_bounds() -> None:
    assert password_problem("x" * (PASSWORD_MIN_LENGTH - 1)) == "too_short"
    assert password_problem("Zx9" + "q" * (PASSWORD_MAX_LENGTH - 2)) == "too_long"
    assert password_problem("correct horse battery") is None


def test_password_rejects_email_and_common() -> None:
    assert password_problem("Ann@Example.com", "ann@example.com") == "equals_email"
    assert password_problem("QWERTYUIOP") == "common"
    assert password_problem("Пароль12345") == "common"


def test_common_list_is_clean() -> None:
    assert all(len(p) >= PASSWORD_MIN_LENGTH for p in common_passwords())


def test_check_password_raises_policy_error() -> None:
    with pytest.raises(IdentityError) as exc:
        check_password("short")
    assert exc.value.code is IdentityErrorCode.password_policy
    check_password("a perfectly fine passphrase")


def test_actor_defaults_stay_backward_compatible() -> None:
    plain = Actor(kind=ActorKind.user, id="u1")
    assert not plain.is_instance_admin
    assert plain.source is None
    assert plain.scopes == frozenset()
    assert Actor.user("u1") == Actor.user("u1", None, None)
    assert Actor.local().source is ActorSource.local
    assert Actor.guest("l1").source is ActorSource.link


def test_actor_server_fields() -> None:
    actor = Actor.user("u1", is_instance_admin=True, source=ActorSource.pat, scopes=frozenset({"api"}))
    assert actor.is_instance_admin
    assert actor.source is ActorSource.pat
    assert actor.key == "u1"
    assert hash(actor) == hash(actor)
