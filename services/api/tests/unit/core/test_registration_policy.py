from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hse_doc_studio.core.identity.entities import AuthSettings, RegistrationInvite, RegistrationMode, UserStatus
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.registration import (
    RegistrationDecision,
    RegistrationOutcome,
    RegistrationPolicy,
    invite_usable,
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
        (M.open, "a@gmail.com", False, False, RegistrationDecision(ST.active, False, True, OUT.check_email)),
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
