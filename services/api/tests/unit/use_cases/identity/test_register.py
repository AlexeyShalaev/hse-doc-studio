from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import timedelta

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.auth_settings import (
    KEY_REGISTRATION_DOMAINS,
    KEY_REGISTRATION_MODE,
    KEY_REQUIRE_APPROVAL,
    AuthEnvOverrides,
)
from hse_doc_studio.core.identity.entities import AuthTokenKind, InviteQuery, MailKind, RegistrationMode, UserStatus
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import hash_token
from hse_doc_studio.core.identity.registration import RegistrationOutcome

from .conftest import FakeSender, World

PASSWORD = "correct horse battery"
ADMIN = Actor.user("admin", is_instance_admin=True)


async def _set(world: World, mode: str, *, approval: bool = False, domains: list[str] | None = None) -> None:
    await world.settings.set(KEY_REGISTRATION_MODE, mode, source="test")
    await world.settings.set(KEY_REQUIRE_APPROVAL, approval, source="test")
    await world.settings.set(KEY_REGISTRATION_DOMAINS, domains or [], source="test")


async def _admin(world: World) -> None:
    await world.add_user("admin@example.org", user_id="admin")


async def _register(world: World, email: str = "new@example.org", token: str | None = None):  # type: ignore[no-untyped-def]
    return await world.register_uc().execute(email, "New", PASSWORD, token)


async def test_open_without_smtp_activates_and_returns_copyable_link(world: World) -> None:
    await _set(world, "open")
    result = await _register(world)
    user = await world.users.get_by_email("new@example.org")
    assert user is not None
    assert (user.status, user.email_verified) == (UserStatus.active, False)
    assert result.outcome is RegistrationOutcome.check_email
    assert result.link is not None
    assert result.link.startswith("https://studio.test/verify/")
    token = result.link.rpartition("/")[2]
    consumed = await world.auth_tokens.consume(hash_token(token), AuthTokenKind.verify_email, world.clock.now)
    assert consumed is not None
    assert consumed.user_id == user.id
    assert [e.kind for e in await world.outbox.list_active(world.clock.now)] == [MailKind.verify_email]
    assert await world.creds.get_hash(user.id)


async def test_open_with_smtp_sends_mail_and_waits_for_verification(world: World) -> None:
    await _set(world, "open")
    world.sender = FakeSender(enabled=True)
    result = await _register(world)
    user = await world.users.get_by_email("new@example.org")
    assert user is not None
    assert user.status is UserStatus.pending_verification
    assert result.link is None
    [(to, _subject, body)] = world.sender.sent
    assert to == "new@example.org"
    assert "https://studio.test/verify/" in body
    assert await world.outbox.list_active(world.clock.now) == []


async def test_smtp_failure_falls_back_to_outbox_link(world: World) -> None:
    await _set(world, "open")
    world.sender = FakeSender(enabled=True, fail=True)
    result = await _register(world)
    assert result.link is not None
    assert len(await world.outbox.list_active(world.clock.now)) == 1


async def test_approval_flag_gives_pending_approval(world: World) -> None:
    await _set(world, "open", approval=True)
    result = await _register(world)
    user = await world.users.get_by_email("new@example.org")
    assert user is not None
    assert user.status is UserStatus.pending_approval
    assert result.outcome is RegistrationOutcome.pending_approval
    assert result.link is None
    assert not user.can_sign_in


async def test_domains_mode_without_smtp_goes_to_approval(world: World) -> None:
    await _set(world, "domains", domains=["hse.ru"])
    result = await _register(world, "ann@hse.ru")
    assert result.outcome is RegistrationOutcome.pending_approval
    with pytest.raises(IdentityError) as exc:
        await _register(world, "ann@gmail.com")
    assert exc.value.code is IdentityErrorCode.domain_not_allowed


@pytest.mark.parametrize(
    ("mode", "code"),
    [("invite", IdentityErrorCode.invitation_required), ("closed", IdentityErrorCode.registration_closed)],
)
async def test_closed_modes_reject_without_invite(world: World, mode: str, code: IdentityErrorCode) -> None:
    await _set(world, mode)
    with pytest.raises(IdentityError) as exc:
        await _register(world)
    assert exc.value.code is code
    assert await world.users.get_by_email("new@example.org") is None


async def test_default_mode_is_invite_only(world: World) -> None:
    with pytest.raises(IdentityError) as exc:
        await _register(world)
    assert exc.value.code is IdentityErrorCode.invitation_required


async def test_weak_password_is_rejected(world: World) -> None:
    await _set(world, "open")
    with pytest.raises(IdentityError) as exc:
        await world.register_uc().execute("new@example.org", "New", "short", None)
    assert exc.value.code is IdentityErrorCode.password_policy


async def test_invite_bypasses_closed_mode_and_is_single_use(world: World) -> None:
    await _admin(world)
    await _set(world, "closed")
    created = await world.create_invite_uc().execute(ADMIN, email="new@example.org", org_id="o1", org_role="member")
    result = await _register(world, " New@Example.org ", created.token)
    user = await world.users.get_by_email("new@example.org")
    assert user is not None
    assert (user.status, user.email_verified) == (UserStatus.active, True)
    assert result.outcome is RegistrationOutcome.active
    assert result.link is None
    stored = await world.invites.get(hash_token(created.token))
    assert stored is not None
    assert stored.used_at == world.clock.now
    with pytest.raises(IdentityError) as exc:
        await _register(world, "new@example.org", created.token)
    assert exc.value.code is IdentityErrorCode.invitation_invalid


async def test_invite_for_other_address_expired_or_unknown(world: World) -> None:
    await _admin(world)
    created = await world.create_invite_uc().execute(ADMIN, email="new@example.org")
    for email, token in (("other@example.org", created.token), ("new@example.org", "nonsense")):
        with pytest.raises(IdentityError) as exc:
            await _register(world, email, token)
        assert exc.value.code is IdentityErrorCode.invitation_invalid
    world.clock.advance(days=8)
    with pytest.raises(IdentityError) as exc:
        await _register(world, "new@example.org", created.token)
    assert exc.value.code is IdentityErrorCode.invitation_invalid
    assert await world.users.get_by_email("new@example.org") is None


async def test_failed_invite_consumption_creates_nobody(world: World) -> None:
    """Приглашение «погасло» между проверкой и записью: в транзакции аккаунт не остаётся."""
    await _admin(world)
    created = await world.create_invite_uc().execute(ADMIN)
    original = world.invites.consume

    async def lost(*args, **kwargs):  # type: ignore[no-untyped-def]
        return None

    world.invites.consume = lost  # type: ignore[method-assign]
    with pytest.raises(IdentityError) as exc:
        await _register(world, "new@example.org", created.token)
    world.invites.consume = original  # type: ignore[method-assign]
    assert exc.value.code is IdentityErrorCode.invitation_invalid


async def test_existing_email_gets_the_same_neutral_answer(world: World) -> None:
    await _set(world, "open")
    await world.add_user("taken@example.org")
    before = await world.users.count()
    hashes = world.hasher.hash_calls
    result = await _register(world, "Taken@Example.org")
    assert result.outcome is RegistrationOutcome.check_email
    assert result.link is None
    assert await world.users.count() == before
    assert world.hasher.hash_calls == hashes + 1
    assert "auth.register_duplicate" in [e.action for e in await world.audit.list()]


async def test_parallel_registration_of_one_email_creates_one_account(world: World) -> None:
    await _set(world, "open")
    results = await asyncio.gather(*(_register(world) for _ in range(6)))
    assert await world.users.count() == 1
    assert {r.outcome for r in results} == {RegistrationOutcome.check_email}
    assert len([r for r in results if r.link]) == 1
    assert len(await world.outbox.list_active(world.clock.now)) == 1


async def test_env_wins_over_database(world: World) -> None:
    await _set(world, "closed")
    world.env = AuthEnvOverrides(registration_mode=RegistrationMode.open)
    result = await _register(world)
    assert result.outcome is RegistrationOutcome.check_email
    # Убрали переменную: снова действует значение админа.
    world.env = AuthEnvOverrides()
    with pytest.raises(IdentityError) as exc:
        await _register(world, "second@example.org")
    assert exc.value.code is IdentityErrorCode.registration_closed


async def test_update_of_locked_key_is_refused_and_unlocked_keys_are_saved(world: World) -> None:
    from hse_doc_studio.use_cases.identity.auth_settings import AuthSettingsPatch

    world.env = AuthEnvOverrides(registration_mode=RegistrationMode.closed)
    uc = world.update_settings_uc()
    with pytest.raises(IdentityError) as exc:
        await uc.execute("admin", AuthSettingsPatch(registration_mode=RegistrationMode.open, require_approval=True))
    assert exc.value.code is IdentityErrorCode.setting_locked
    assert dict(await world.settings.get_all()) == {}

    view = await uc.execute(
        "admin", AuthSettingsPatch(require_approval=True, registration_domains=[" @HSE.ru", "hse.ru", ""])
    )
    assert view.settings.registration_mode is RegistrationMode.closed
    assert view.settings.require_approval is True
    assert view.settings.registration_domains == ("hse.ru",)
    assert view.locked == {KEY_REGISTRATION_MODE}
    assert [e.action for e in await world.audit.list()] == ["settings.auth_update"]


async def test_invite_lifecycle_create_list_revoke(world: World) -> None:
    await _admin(world)
    plain = await world.create_invite_uc().execute(ADMIN)
    assert plain.link is not None
    assert plain.link.startswith("https://studio.test/invite/")
    assert await world.outbox.list_active(world.clock.now) == []
    mailed = await world.create_invite_uc().execute(ADMIN, email="Bob@Example.org", ttl=timedelta(days=1))
    assert mailed.link is not None  # без SMTP ссылку пересылает админ
    assert [e.to_email for e in await world.outbox.list_active(world.clock.now)] == ["bob@example.org"]
    assert {i.id for i in (await world.list_invites_uc().execute(ADMIN, InviteQuery(now=world.clock.now))).items} == {
        plain.invite.id,
        mailed.invite.id,
    }

    info = await world.invitation_info_uc().execute(mailed.token)
    assert (info.email, info.invited_by) == ("bob@example.org", "Ann")

    await world.revoke_invite_uc().execute(ADMIN, plain.invite.id)
    assert [i.id for i in (await world.list_invites_uc().execute(ADMIN, InviteQuery(now=world.clock.now))).items] == [
        mailed.invite.id
    ]
    with pytest.raises(IdentityError) as exc:
        await world.revoke_invite_uc().execute(ADMIN, plain.invite.id)
    assert exc.value.code is IdentityErrorCode.invitation_invalid
    with pytest.raises(IdentityError):
        await world.invitation_info_uc().execute(plain.token)
    assert {"invite.create", "invite.revoke"} <= {e.action for e in await world.audit.list()}


async def test_invite_with_smtp_is_mailed_not_shown(world: World) -> None:
    await _admin(world)
    world.sender = FakeSender(enabled=True)
    created = await world.create_invite_uc().execute(ADMIN, email="bob@example.org")
    assert created.link is None
    assert [to for to, _, _ in world.sender.sent] == ["bob@example.org"]


async def test_only_instance_admin_manages_invites(world: World) -> None:
    await _admin(world)
    member = replace(ADMIN, is_instance_admin=False)
    for call in (
        world.create_invite_uc().execute(member),
        world.list_invites_uc().execute(member, InviteQuery(now=world.clock.now)),
        world.revoke_invite_uc().execute(member, "x"),
    ):
        with pytest.raises(IdentityError) as exc:
            await call
        assert exc.value.code is IdentityErrorCode.forbidden


@pytest.mark.parametrize(
    "kwargs",
    [{"email": "nope"}, {"org_role": "member"}, {"org_id": "o1"}, {"ttl": timedelta(0)}, {"ttl": timedelta(days=90)}],
)
async def test_invalid_invite_parameters(world: World, kwargs: dict[str, object]) -> None:
    await _admin(world)
    with pytest.raises(IdentityError) as exc:
        await world.create_invite_uc().execute(ADMIN, **kwargs)  # type: ignore[arg-type]
    assert exc.value.code is IdentityErrorCode.invitation_invalid
