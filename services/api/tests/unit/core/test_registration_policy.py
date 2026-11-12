from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hse_doc_studio.core.identity.entities import AuthSettings, RegistrationInvite, RegistrationMode, User, UserStatus
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.registration import (
    RegistrationDecision,
    RegistrationOutcome,
    RegistrationPolicy,
    invite_usable,
    status_after_verification,
)

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
OUT = RegistrationOutcome
ST = UserStatus
M = RegistrationMode
CODE = IdentityErrorCode

PLAIN = RegistrationInvite("h", None, "admin", NOW + timedelta(days=1))
BOUND = RegistrationInvite("h", "ann@hse.ru", "admin", NOW + timedelta(days=1))


def _policy(mode: RegistrationMode, *, approval: bool = False, smtp: bool = True) -> RegistrationPolicy:
    settings = AuthSettings(registration_mode=mode, registration_domains=("hse.ru",), require_approval=approval)
    return RegistrationPolicy(settings, smtp_enabled=smtp)


def _ok(mode: RegistrationMode, email: str, invite: RegistrationInvite | None, **kw: bool) -> RegistrationDecision:
    return _policy(mode, **kw).evaluate(email, invite)


@pytest.mark.parametrize(
    ("mode", "email", "invite", "code"),
    [
        (M.closed, "ann@hse.ru", None, CODE.registration_closed),
        (M.invite, "ann@hse.ru", None, CODE.invitation_required),
        (M.domains, "ann@gmail.com", None, CODE.domain_not_allowed),
        (M.domains, "ann@HSE.ru.evil.org", None, CODE.domain_not_allowed),
        (M.open, "not-an-email", None, CODE.domain_not_allowed),
        (M.open, "not-an-email", PLAIN, CODE.domain_not_allowed),
    ],
)
def test_rejections(
    mode: RegistrationMode, email: str, invite: RegistrationInvite | None, code: IdentityErrorCode
) -> None:
    with pytest.raises(IdentityError) as exc:
        _ok(mode, email, invite)
    assert exc.value.code is code


def test_open_without_smtp_and_without_invite_requires_one() -> None:
    """Без SMTP анонимную почту не подтвердить, а ссылку показать нельзя: open без приглашения — тупик."""
    with pytest.raises(IdentityError) as exc:
        _ok(M.open, "a@gmail.com", None, smtp=False)
    assert exc.value.code is CODE.invitation_required


@pytest.mark.parametrize("mode", list(RegistrationMode))
@pytest.mark.parametrize("email", ["ann@hse.ru", "ann@gmail.com"])
@pytest.mark.parametrize("approval", [False, True])
def test_valid_invite_opens_every_mode_and_skips_approval(mode: RegistrationMode, email: str, approval: bool) -> None:
    decision = _ok(mode, email, BOUND, approval=approval)
    assert decision == RegistrationDecision(ST.active, True, False, OUT.active)


@pytest.mark.parametrize("smtp", [True, False])
def test_unbound_invite_does_not_prove_the_address(smtp: bool) -> None:
    decision = _ok(M.invite, "ann@gmail.com", PLAIN, approval=True, smtp=smtp)
    status = ST.pending_verification if smtp else ST.active
    assert decision == RegistrationDecision(status, False, True, OUT.check_email)


@pytest.mark.parametrize(
    ("mode", "email", "approval", "smtp", "expected"),
    [
        (
            M.open,
            "a@gmail.com",
            False,
            True,
            RegistrationDecision(ST.pending_verification, False, True, OUT.check_email),
        ),
        (
            M.open,
            "a@gmail.com",
            True,
            True,
            RegistrationDecision(ST.pending_approval, False, True, OUT.pending_approval),
        ),
        (
            M.open,
            "a@gmail.com",
            True,
            False,
            RegistrationDecision(ST.pending_approval, False, False, OUT.pending_approval),
        ),
        (
            M.domains,
            "a@hse.ru",
            False,
            True,
            RegistrationDecision(ST.pending_verification, False, True, OUT.check_email),
        ),
        # Без SMTP владение доменом не проверить: решает админ.
        (
            M.domains,
            "a@hse.ru",
            False,
            False,
            RegistrationDecision(ST.pending_approval, False, False, OUT.pending_approval),
        ),
        (
            M.domains,
            "a@hse.ru",
            True,
            True,
            RegistrationDecision(ST.pending_approval, False, True, OUT.pending_approval),
        ),
        (
            M.domains,
            "A@HSE.RU",
            False,
            True,
            RegistrationDecision(ST.pending_verification, False, True, OUT.check_email),
        ),
    ],
)
def test_self_registration_matrix(
    mode: RegistrationMode, email: str, approval: bool, smtp: bool, expected: RegistrationDecision
) -> None:
    assert _ok(mode, email, None, approval=approval, smtp=smtp) == expected


def test_invite_usable() -> None:
    assert invite_usable(BOUND, " ANN@hse.ru ", NOW)
    assert not invite_usable(BOUND, "bob@hse.ru", NOW)
    assert invite_usable(PLAIN, "anyone@x.org", NOW)
    assert not invite_usable(PLAIN, "anyone@x.org", NOW + timedelta(days=1))
    used = RegistrationInvite("h", None, "admin", NOW + timedelta(days=1), used_at=NOW)
    assert not invite_usable(used, "anyone@x.org", NOW)


# ---- Исключения из одобрения ----

EXEMPT = ("hse.ru", "*.hse.ru", "boss@gmail.com")


def _exempting(
    mode: RegistrationMode, *, approval: bool = True, smtp: bool = True, domains: tuple[str, ...] = ("hse.ru",)
) -> RegistrationPolicy:
    settings = AuthSettings(
        registration_mode=mode, registration_domains=domains, require_approval=approval, approval_exemptions=EXEMPT
    )
    return RegistrationPolicy(settings, smtp_enabled=smtp)


@pytest.mark.parametrize(
    ("email", "rule"), [("ann@hse.ru", "hse.ru"), ("ann@edu.hse.ru", "*.hse.ru"), ("Boss@Gmail.com", "boss@gmail.com")]
)
def test_open_with_approval__exempt_address_goes_through_email_check_not_the_queue(email: str, rule: str) -> None:
    decision = _exempting(M.open).evaluate(email)

    assert decision == RegistrationDecision(ST.pending_verification, False, True, OUT.check_email, exemption=rule)


@pytest.mark.parametrize("email", ["ann@nothse.ru", "ann@hse.ru.evil.com", "other@gmail.com"])
def test_open_with_approval__other_addresses_still_wait_for_approval(email: str) -> None:
    decision = _exempting(M.open).evaluate(email)

    assert decision == RegistrationDecision(ST.pending_approval, False, True, OUT.pending_approval)


def test_domains_mode__domain_is_checked_before_the_exemption() -> None:
    policy = _exempting(M.domains, domains=("hse.ru", "edu.hse.ru"))

    assert policy.evaluate("ann@edu.hse.ru").exemption == "*.hse.ru"
    assert policy.evaluate("ann@hse.ru").status is ST.pending_verification
    # Адрес из исключений, но домен не разрешён: регистрации нет вовсе.
    with pytest.raises(IdentityError) as exc:
        policy.evaluate("boss@gmail.com")
    assert exc.value.code is CODE.domain_not_allowed


@pytest.mark.parametrize("mode", [M.open, M.domains])
def test_without_smtp_the_exemption_does_not_apply(mode: RegistrationMode) -> None:
    """Без SMTP адрес не подтвердить: иначе любой назвался бы чужим @hse.ru и обошёл одобрение."""
    decision = _exempting(mode, smtp=False).evaluate("ann@hse.ru")

    assert decision == RegistrationDecision(ST.pending_approval, False, False, OUT.pending_approval)


def test_without_approval_exemptions_change_nothing() -> None:
    decision = _exempting(M.open, approval=False).evaluate("ann@hse.ru")

    assert decision == RegistrationDecision(ST.pending_verification, False, True, OUT.check_email)
    assert _exempting(M.open, approval=False).approval_exemption("ann@hse.ru") is None


@pytest.mark.parametrize("mode", [M.closed, M.invite])
def test_exemptions_do_not_open_closed_modes(mode: RegistrationMode) -> None:
    with pytest.raises(IdentityError):
        _exempting(mode).evaluate("ann@hse.ru")


def test_invites_are_untouched_by_exemptions() -> None:
    assert _exempting(M.invite).evaluate("ann@hse.ru", PLAIN) == RegistrationDecision(
        ST.pending_verification, False, True, OUT.check_email
    )


def test_external_login__provider_verified_email_skips_approval_by_rule() -> None:
    policy = _exempting(M.open)

    assert policy.evaluate_external("ann@edu.hse.ru") == RegistrationDecision(
        ST.active, True, False, OUT.active, exemption="*.hse.ru"
    )
    assert policy.evaluate_external("ann@gmail.com") == RegistrationDecision(
        ST.pending_approval, True, False, OUT.pending_approval
    )
    assert _exempting(M.open, approval=False).evaluate_external("ann@hse.ru").exemption is None
    with pytest.raises(IdentityError):
        _exempting(M.domains).evaluate_external("boss@gmail.com")


def _user(status: UserStatus, email: str = "ann@hse.ru", rule: str | None = None) -> User:
    return User("u1", email, email, "Ann", status, NOW, approval_exempt_rule=rule)


def _settings(*, approval: bool = True, rules: tuple[str, ...] = EXEMPT) -> AuthSettings:
    return AuthSettings(registration_mode=M.open, require_approval=approval, approval_exemptions=rules)


def test_after_verification__exempt_registration_becomes_active_by_the_current_rule() -> None:
    assert status_after_verification(_settings(), _user(ST.pending_verification, rule="hse.ru")) == (
        ST.active,
        "hse.ru",
    )


def test_after_verification__removed_rule_sends_the_account_to_the_queue() -> None:
    user = _user(ST.pending_verification, rule="hse.ru")

    assert status_after_verification(_settings(rules=("*.hse.ru",)), user) == (ST.pending_approval, None)
    # Одобрение выключили совсем: ждать некого.
    assert status_after_verification(_settings(approval=False, rules=()), user) == (ST.active, None)


def test_after_verification__rule_added_later_releases_a_queued_account() -> None:
    assert status_after_verification(_settings(), _user(ST.pending_approval)) == (ST.active, "hse.ru")
    assert status_after_verification(_settings(), _user(ST.pending_approval, "ann@gmail.com")) == (
        ST.pending_approval,
        None,
    )
    assert status_after_verification(_settings(approval=False), _user(ST.pending_approval)) == (
        ST.pending_approval,
        None,
    )


def test_after_verification__plain_pending_verification_is_as_before() -> None:
    """Без пометки исключения (приглашение без адреса, регистрация без одобрения) письмо делает аккаунт активным."""
    assert status_after_verification(_settings(rules=()), _user(ST.pending_verification)) == (ST.active, None)
    assert status_after_verification(_settings(), _user(ST.pending_verification)) == (ST.active, None)
    assert status_after_verification(_settings(), _user(ST.disabled)) == (ST.disabled, None)
