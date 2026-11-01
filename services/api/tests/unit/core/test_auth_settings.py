from __future__ import annotations

import pytest
from hse_doc_studio.core.identity.auth_settings import (
    KEY_PASSWORD_ENABLED,
    KEY_REGISTRATION_DOMAINS,
    KEY_REGISTRATION_MODE,
    auth_settings_from,
)
from hse_doc_studio.core.identity.entities import RegistrationMode
from hse_doc_studio.core.identity.normalize import avatar_initials


def test_defaults_are_invite_only_with_password() -> None:
    result = auth_settings_from({})

    assert result.registration_mode is RegistrationMode.invite
    assert result.password_enabled is True
    assert result.registration_domains == ()


def test_stored_values_are_read() -> None:
    result = auth_settings_from(
        {KEY_REGISTRATION_MODE: "domains", KEY_REGISTRATION_DOMAINS: ["hse.ru"], KEY_PASSWORD_ENABLED: False}
    )

    assert result.registration_mode is RegistrationMode.domains
    assert result.registration_domains == ("hse.ru",)
    assert result.password_enabled is False


@pytest.mark.parametrize("junk", ["everyone", 5, None, ["open"]])
def test_unknown_mode_falls_back_to_invite(junk: object) -> None:
    assert auth_settings_from({KEY_REGISTRATION_MODE: junk}).registration_mode is RegistrationMode.invite


@pytest.mark.parametrize(
    ("name", "email", "expected"),
    [
        ("Анна Петрова", "a@b.co", "АП"),
        ("ivan", "a@b.co", "I"),
        ("  мария  ивановна  сидорова ", "a@b.co", "МИ"),
        ("", "zed@b.co", "Z"),
        ("", "", "?"),
    ],
)
def test_avatar_initials(name: str, email: str, expected: str) -> None:
    assert avatar_initials(name, email) == expected


def test_env_wins_over_stored_values_and_locks_only_set_keys() -> None:
    from hse_doc_studio.core.identity.auth_settings import (
        KEY_REGISTRATION_MODE,
        KEY_REQUIRE_APPROVAL,
        AuthEnvOverrides,
        effective_auth_settings,
    )

    stored = {KEY_REGISTRATION_MODE: "closed", KEY_REQUIRE_APPROVAL: True, KEY_REGISTRATION_DOMAINS: ["a.org"]}
    env = AuthEnvOverrides(registration_mode=RegistrationMode.open, registration_domains=(" @HSE.ru", "hse.ru"))

    result = effective_auth_settings(stored, env)

    assert result.registration_mode is RegistrationMode.open
    assert result.registration_domains == ("hse.ru",)
    assert result.require_approval is True
    assert env.locked_keys() == {KEY_REGISTRATION_MODE, KEY_REGISTRATION_DOMAINS}


def test_empty_env_domain_list_is_still_a_lock() -> None:
    from hse_doc_studio.core.identity.auth_settings import AuthEnvOverrides, effective_auth_settings

    env = AuthEnvOverrides(registration_domains=())
    assert effective_auth_settings({KEY_REGISTRATION_DOMAINS: ["a.org"]}, env).registration_domains == ()
    assert KEY_REGISTRATION_DOMAINS in env.locked_keys()
