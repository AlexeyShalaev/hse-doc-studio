from __future__ import annotations

from datetime import timedelta

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.entities import MailKind, Session, UserStatus
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import hash_token
from hse_doc_studio.use_cases.identity.recovery import ADMIN_RESET_TTL, RESET_TTL, VERIFY_TTL

from .conftest import T0, FakeSender, World

NEW_PASSWORD = "a much longer new passphrase"
ADMIN = Actor.user("admin", is_instance_admin=True)


def _token(body: str) -> str:
    return body.strip().splitlines()[1].rpartition("/")[2]


async def _unverified(world: World, status: UserStatus = UserStatus.active) -> str:
    user = await world.add_user(status=status)
    await world.users.update(_unverify(user))
    return user.id


def _unverify(user):  # type: ignore[no-untyped-def]
    from dataclasses import replace

    return replace(user, email_verified=False)


async def _mail_token(world: World, kind: MailKind) -> str:
    (sent,) = list(world.sender.sent)
    return _token(sent[2])


async def _expect(coro, code: IdentityErrorCode) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(IdentityError) as caught:
        await coro
    assert caught.value.code is code


# --- подтверждение почты ---


async def test_verify_marks_email_and_activates_a_pending_account(world: World) -> None:
    world.sender = FakeSender(enabled=True)
    user_id = await _unverified(world, UserStatus.pending_verification)
    await world.resend_uc().execute("ann@example.org")

    await world.verify_uc().execute(await _mail_token(world, MailKind.verify_email))

    user = await world.users.get(user_id)
    assert user is not None
    assert (user.email_verified, user.status) == (True, UserStatus.active)
    assert "auth.email_verified" in [e.action for e in await world.audit.list()]


async def test_verify_keeps_the_approval_wait(world: World) -> None:
    world.sender = FakeSender(enabled=True)
    user_id = await _unverified(world, UserStatus.pending_approval)
    await world.resend_uc().execute("ann@example.org")

    await world.verify_uc().execute(await _mail_token(world, MailKind.verify_email))

    user = await world.users.get(user_id)
    assert user is not None
    assert (user.email_verified, user.status) == (True, UserStatus.pending_approval)


async def test_verify_token_is_single_use(world: World) -> None:
    world.sender = FakeSender(enabled=True)
    await _unverified(world)
    await world.resend_uc().execute("ann@example.org")
    token = await _mail_token(world, MailKind.verify_email)

    await world.verify_uc().execute(token)

    await _expect(world.verify_uc().execute(token), IdentityErrorCode.token_invalid)


async def test_verify_expired_token_is_refused(world: World) -> None:
    world.sender = FakeSender(enabled=True)
    await _unverified(world)
    await world.resend_uc().execute("ann@example.org")
    token = await _mail_token(world, MailKind.verify_email)

    world.clock.advance(seconds=VERIFY_TTL.total_seconds() + 1)

    await _expect(world.verify_uc().execute(token), IdentityErrorCode.token_invalid)


async def test_verify_garbage_and_wrong_kind_get_the_same_refusal(world: World) -> None:
    world.sender = FakeSender(enabled=True)
    await world.add_user()
    await world.forgot_uc().execute("ann@example.org")
    reset_token = await _mail_token(world, MailKind.reset_password)

    await _expect(world.verify_uc().execute("nope"), IdentityErrorCode.token_invalid)
    await _expect(world.verify_uc().execute(reset_token), IdentityErrorCode.token_invalid)


async def test_resend_sends_only_to_unverified_accounts(world: World) -> None:
    world.sender = FakeSender(enabled=True)
    await world.add_user("done@example.org", user_id="done")
    await world.add_user("off@example.org", user_id="off", status=UserStatus.disabled)

    for email in ("done@example.org", "off@example.org", "nobody@example.org"):
        await world.resend_uc().execute(email)

    assert world.sender.sent == []


async def test_resend_without_smtp_goes_to_outbox_not_to_the_caller(world: World) -> None:
    await _unverified(world)

    result = await world.resend_uc().execute("ANN@example.org")

    assert result is None
    (entry,) = await world.outbox.list_active(T0)
    assert entry.kind is MailKind.verify_email
    assert entry.link.startswith("https://studio.test/verify/")


# --- забыл пароль и сброс ---


async def test_forgot_mails_a_link_that_resets_the_password_once(world: World) -> None:
    world.sender = FakeSender(enabled=True)
    user = await world.add_user()
    await world.sessions.add(
        Session(hash_token("s1"), user.id, "c", T0, T0, T0 + timedelta(days=1)),
    )

    await world.forgot_uc().execute("Ann@Example.org")
    (to, subject, body) = world.sender.sent[0]
    assert (to, subject) == ("ann@example.org", "Сброс пароля")
    assert "https://studio.test/reset/" in body
    token = _token(body)

    await world.reset_uc().execute(token, NEW_PASSWORD)

    stored = await world.creds.get_hash(user.id)
    assert stored is not None
    assert world.hasher.verify(NEW_PASSWORD, stored)
    assert await world.sessions.list_for_user(user.id) == []
    assert "auth.password_reset" in [e.action for e in await world.audit.list()]
    await _expect(world.reset_uc().execute(token, NEW_PASSWORD), IdentityErrorCode.token_invalid)


async def test_forgot_mail_follows_the_account_language(world: World) -> None:
    world.sender = FakeSender(enabled=True)
    user = await world.add_user()
    from dataclasses import replace

    await world.users.update(replace(user, locale="en"))

    await world.forgot_uc().execute("ann@example.org")

    assert world.sender.sent[0][1] == "Password reset"


async def test_newer_reset_link_invalidates_the_older_one(world: World) -> None:
    world.sender = FakeSender(enabled=True)
    await world.add_user()

    await world.forgot_uc().execute("ann@example.org")
    await world.forgot_uc().execute("ann@example.org")
    first, second = (_token(body) for (_to, _subject, body) in world.sender.sent)

    await _expect(world.reset_uc().execute(first, NEW_PASSWORD), IdentityErrorCode.token_invalid)
    await world.reset_uc().execute(second, NEW_PASSWORD)


async def test_new_admin_link_replaces_the_mailed_one_and_reset_spends_it(world: World) -> None:
    world.sender = FakeSender(enabled=True)
    user = await world.add_user()
    await world.forgot_uc().execute("ann@example.org")
    mailed = _token(world.sender.sent[0][2])
    admin_link = await world.issue_reset_link_uc().execute(ADMIN, user.id, confirmed=True)
    admin_token = admin_link.link.rpartition("/")[2]

    await _expect(world.reset_uc().execute(mailed, NEW_PASSWORD), IdentityErrorCode.token_invalid)
    await world.reset_uc().execute(admin_token, NEW_PASSWORD)

    await _expect(world.reset_uc().execute(admin_token, NEW_PASSWORD), IdentityErrorCode.token_invalid)


async def test_forgot_is_indistinguishable_for_known_unknown_and_disabled(world: World) -> None:
    await world.add_user("ann@example.org")
    await world.add_user("off@example.org", user_id="off", status=UserStatus.disabled)

    results = [
        await world.forgot_uc().execute(email) for email in ("ann@example.org", "ghost@example.org", "off@example.org")
    ]

    assert results == [None, None, None]
    # Без SMTP письмо остаётся в outbox для администратора: на экран ссылка не попадает ни для кого.
    assert [e.to_email for e in await world.outbox.list_active(T0)] == ["ann@example.org"]


async def test_forgot_smtp_failure_falls_back_to_outbox(world: World) -> None:
    world.sender = FakeSender(enabled=True, fail=True)
    await world.add_user()

    assert await world.forgot_uc().execute("ann@example.org") is None

    (entry,) = await world.outbox.list_active(T0)
    assert entry.kind is MailKind.reset_password


async def test_reset_token_expires(world: World) -> None:
    await world.add_user()
    await world.forgot_uc().execute("ann@example.org")
    (entry,) = await world.outbox.list_active(T0)
    token = entry.link.rpartition("/")[2]

    world.clock.advance(seconds=RESET_TTL.total_seconds() + 1)

    await _expect(world.reset_uc().execute(token, NEW_PASSWORD), IdentityErrorCode.token_invalid)


async def test_reset_rejects_a_weak_password_before_spending_the_token(world: World) -> None:
    await world.add_user()
    await world.forgot_uc().execute("ann@example.org")
    (entry,) = await world.outbox.list_active(T0)
    token = entry.link.rpartition("/")[2]

    await _expect(world.reset_uc().execute(token, "short"), IdentityErrorCode.password_policy)
    await _expect(world.reset_uc().execute(token, "password123456"), IdentityErrorCode.password_policy)

    await world.reset_uc().execute(token, NEW_PASSWORD)


async def test_reset_password_equal_to_the_email_is_refused(world: World) -> None:
    await world.add_user("long.address@example.org")
    await world.forgot_uc().execute("long.address@example.org")
    (entry,) = await world.outbox.list_active(T0)

    await _expect(
        world.reset_uc().execute(entry.link.rpartition("/")[2], "long.address@example.org"),
        IdentityErrorCode.password_policy,
    )


async def test_reset_refuses_when_the_account_was_disabled_meanwhile(world: World) -> None:
    from dataclasses import replace

    user = await world.add_user()
    await world.forgot_uc().execute("ann@example.org")
    (entry,) = await world.outbox.list_active(T0)
    await world.users.update(replace(user, status=UserStatus.disabled))

    await _expect(
        world.reset_uc().execute(entry.link.rpartition("/")[2], NEW_PASSWORD), IdentityErrorCode.token_invalid
    )


# --- ссылка от администратора ---


async def test_admin_reset_link_is_audited_and_resets_the_password(world: World) -> None:
    world.sender = FakeSender(enabled=True)
    user = await world.add_user()

    result = await world.issue_reset_link_uc().execute(ADMIN, user.id, confirmed=True)

    assert result.link.startswith("https://studio.test/reset/")
    assert result.expires_at == T0 + ADMIN_RESET_TTL
    assert result.user_notified
    (to, subject, _body) = world.sender.sent[0]
    assert (to, subject) == ("ann@example.org", "Администратор выдал ссылку для сброса пароля")
    (event,) = [e for e in await world.audit.list() if e.action == "admin.reset_link_issued"]
    assert (event.actor_id, event.target) == ("admin", user.id)
    assert event.details == {"break_glass": True}

    await world.reset_uc().execute(result.link.rpartition("/")[2], NEW_PASSWORD)


async def test_admin_reset_link_without_smtp_is_not_mailed(world: World) -> None:
    user = await world.add_user()

    result = await world.issue_reset_link_uc().execute(ADMIN, user.id, confirmed=True)

    assert not result.user_notified
    assert result.link


async def test_admin_reset_link_needs_admin_and_confirmation(world: World) -> None:
    user = await world.add_user()

    await _expect(
        world.issue_reset_link_uc().execute(Actor.user("u2"), user.id, confirmed=True), IdentityErrorCode.forbidden
    )
    await _expect(world.issue_reset_link_uc().execute(ADMIN, user.id, confirmed=False), IdentityErrorCode.forbidden)
    await _expect(world.issue_reset_link_uc().execute(ADMIN, "ghost", confirmed=True), IdentityErrorCode.forbidden)
    assert [e.action for e in await world.audit.list()] == []
