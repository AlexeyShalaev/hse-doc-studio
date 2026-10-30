from __future__ import annotations

import pytest
from hse_doc_studio.core.identity.entities import MailKind
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.use_cases.identity.account_email import CHANGE_TTL

from .conftest import T0, FakeSender, World

PASSWORD = "correct horse battery"


async def _request(world: World, new_email: str = "Anna@New.example.org"):  # type: ignore[no-untyped-def]
    return await world.request_email_change_uc().execute("u1", PASSWORD, new_email)


async def test_link_goes_to_the_new_address_and_confirms_the_change(world: World) -> None:
    world.sender = FakeSender(enabled=True)
    await world.add_user()

    result = await _request(world)

    assert result.link is None
    (to, subject, body) = world.sender.sent[0]
    assert (to, subject) == ("Anna@New.example.org", "Подтвердите новый e-mail")
    user = await world.users.get("u1")
    assert user is not None
    assert user.email == "ann@example.org"
    token = body.splitlines()[1].rpartition("/")[2]

    await world.confirm_email_change_uc().execute(token)

    user = await world.users.get("u1")
    assert user is not None
    assert (user.email, user.email_normalized, user.email_verified) == (
        "Anna@New.example.org",
        "anna@new.example.org",
        True,
    )
    assert await world.users.get_by_email("ann@example.org") is None
    assert {"auth.email_change_requested", "auth.email_changed"} <= {e.action for e in await world.audit.list()}


async def test_without_smtp_the_link_is_returned_and_kept_in_outbox(world: World) -> None:
    await world.add_user()

    result = await _request(world)

    assert result.link is not None
    assert result.link.startswith("https://studio.test/confirm-email/")
    (entry,) = await world.outbox.list_active(T0)
    assert (entry.kind, entry.to_email) == (MailKind.email_change, "Anna@New.example.org")


async def test_wrong_password_is_refused_and_nothing_is_issued(world: World) -> None:
    await world.add_user()

    with pytest.raises(IdentityError) as caught:
        await world.request_email_change_uc().execute("u1", "wrong password!!", "new@example.org")

    assert caught.value.code is IdentityErrorCode.invalid_credentials
    assert await world.outbox.list_active(T0) == []


async def test_taken_address_answers_like_a_free_one_but_sends_nothing(world: World) -> None:
    world.sender = FakeSender(enabled=True)
    await world.add_user()
    await world.add_user("busy@example.org", user_id="u2")

    result = await _request(world, "BUSY@example.org")

    assert result.link is None
    assert world.sender.sent == []


async def test_same_address_is_a_quiet_noop(world: World) -> None:
    await world.add_user()

    result = await _request(world, "ANN@example.org")

    assert result.link is None
    assert await world.outbox.list_active(T0) == []


async def test_token_is_single_use_and_expires(world: World) -> None:
    await world.add_user()
    link = (await _request(world)).link
    assert link is not None
    token = link.rpartition("/")[2]
    await world.confirm_email_change_uc().execute(token)

    with pytest.raises(IdentityError) as again:
        await world.confirm_email_change_uc().execute(token)
    assert again.value.code is IdentityErrorCode.token_invalid

    second = (await _request(world, "other@example.org")).link
    assert second is not None
    world.clock.advance(seconds=CHANGE_TTL.total_seconds() + 1)
    with pytest.raises(IdentityError) as late:
        await world.confirm_email_change_uc().execute(second.rpartition("/")[2])
    assert late.value.code is IdentityErrorCode.token_invalid


async def test_address_taken_between_request_and_confirmation(world: World) -> None:
    await world.add_user()
    link = (await _request(world, "race@example.org")).link
    assert link is not None
    await world.add_user("race@example.org", user_id="u2")

    with pytest.raises(IdentityError) as caught:
        await world.confirm_email_change_uc().execute(link.rpartition("/")[2])

    assert caught.value.code is IdentityErrorCode.email_taken
    user = await world.users.get("u1")
    assert user is not None
    assert user.email == "ann@example.org"


async def test_a_verification_token_cannot_confirm_an_email_change(world: World) -> None:
    await world.add_user()
    await world.forgot_uc().execute("ann@example.org")
    (entry,) = await world.outbox.list_active(T0)

    with pytest.raises(IdentityError):
        await world.confirm_email_change_uc().execute(world.links[-1].rpartition("/")[2])
