"""Сценарии passkey: регистрация, вход, повторное подтверждение, удаление и админка на настоящей проверке подписей."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest
from hse_doc_studio.core.access.entities import Actor, ActorKind, ActorSource
from hse_doc_studio.core.identity.auth_settings import KEY_PASSKEYS_ENABLED, KEY_PASSWORD_ENABLED
from hse_doc_studio.core.identity.entities import AuditEntry, RegistrationInvite, UserIdentity, UserStatus
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import hash_token
from hse_doc_studio.core.identity.passkeys import PASSKEY_LIMIT, RelyingParty
from hse_doc_studio.use_cases.identity.oidc_identities import UnlinkOidcIdentityUC

from tests.fakes.authenticator import SoftAuthenticator, b64url

from .conftest import FakeSender, World
from .passkey_kit import PARTY, PasskeyKit

PASSWORD = "correct horse battery"


@pytest.fixture
def kit(world: World) -> PasskeyKit:
    return PasskeyKit(world)


async def _code(coro: object) -> IdentityErrorCode:
    with pytest.raises(IdentityError) as exc:
        await coro  # type: ignore[misc]
    return exc.value.code


def _ids(options: dict[str, object], key: str) -> list[object]:
    items = options[key]
    assert isinstance(items, list)
    return [item["id"] for item in items]


async def _entries(world: World) -> list[AuditEntry]:
    """События журнала, старые первыми."""
    return list(reversed(await world.audit.list(limit=10_000)))


async def _reasons(world: World, action: str) -> list[object]:
    return [e.details.get("reason") for e in await _entries(world) if e.action == action]


async def test__register__fresh_session__stores_key_bound_to_domain(kit: PasskeyKit, world: World) -> None:
    user = await world.add_user()

    passkey = await kit.register(user, name="  MacBook   Анны ")

    stored = await kit.passkeys.list_for_user(user.id)
    assert stored == [passkey]
    assert passkey.name == "MacBook Анны"
    assert passkey.rp_id == "studio.test"
    assert passkey.credential_id == kit.phone.credentials[0].id
    assert passkey.transports == ("internal", "hybrid")
    assert [e.action for e in (await _entries(world))] == ["auth.passkey_added"]


async def test__register__options__exclude_existing_and_require_uv(kit: PasskeyKit, world: World) -> None:
    user = await world.add_user()
    first = await kit.register(user)
    session = await kit.session(user)

    options = await kit.start_registration().execute(user.id, session, PARTY)

    assert _ids(options, "excludeCredentials") == [first.credential_id]
    assert options["authenticatorSelection"] == {
        "residentKey": "required",
        "requireResidentKey": True,
        "userVerification": "required",
    }
    assert options["attestation"] == "none"
    assert options["user"]["id"] == b64url(user.id.encode())  # type: ignore[index]


async def test__register__stale_session__needs_reauth(kit: PasskeyKit, world: World) -> None:
    user = await world.add_user()
    session = await kit.session(user, minutes_ago=11)

    assert await _code(kit.start_registration().execute(user.id, session, PARTY)) is IdentityErrorCode.reauth_required

    await kit.reauth_uc().execute(user.id, session, PARTY, password=PASSWORD)
    assert await kit.start_registration().execute(user.id, session, PARTY)


async def test__register__default_name_when_empty(kit: PasskeyKit, world: World) -> None:
    user = await world.add_user()
    session = await kit.session(user)
    options = await kit.start_registration().execute(user.id, session, PARTY)

    passkey = await kit.finish_registration().execute(
        user.id, PARTY, kit.phone.create(options), name="   ", fallback_name="Chrome · macOS"
    )

    assert passkey.name == "Chrome · macOS"


async def test__register__response_replayed__rejected(kit: PasskeyKit, world: World) -> None:
    user = await world.add_user()
    session = await kit.session(user)
    response = kit.phone.create(await kit.start_registration().execute(user.id, session, PARTY))
    await kit.finish_registration().execute(user.id, PARTY, response, name=None)

    code = await _code(kit.finish_registration().execute(user.id, PARTY, response, name=None))

    assert code is IdentityErrorCode.passkey_invalid
    assert await _reasons(world, "auth.passkey_add_failed") == ["challenge"]


async def test__register__challenge_of_another_person__rejected(kit: PasskeyKit, world: World) -> None:
    ann = await world.add_user()
    bob = await world.add_user("bob@example.org", user_id="u2")
    options = await kit.start_registration().execute(ann.id, await kit.session(ann), PARTY)

    code = await _code(kit.finish_registration().execute(bob.id, PARTY, kit.phone.create(options), name=None))

    assert code is IdentityErrorCode.passkey_invalid
    assert await kit.passkeys.list_for_user(bob.id) == []


@pytest.mark.parametrize(
    ("tamper", "reason"),
    [
        ({"origin": "https://evil.test"}, "signature"),
        ({"rp_id": "evil.test"}, "signature"),
        ({"uv": False}, "signature"),
    ],
    ids=["foreign_origin", "foreign_rp_id", "no_user_verification"],
)
async def test__register__bad_response__rejected(
    kit: PasskeyKit, world: World, tamper: dict[str, object], reason: str
) -> None:
    user = await world.add_user()
    options = await kit.start_registration().execute(user.id, await kit.session(user), PARTY)

    with pytest.raises(IdentityError) as exc:
        await kit.finish_registration().execute(user.id, PARTY, kit.phone.create(options, **tamper), name=None)  # type: ignore[arg-type]

    assert exc.value.code is IdentityErrorCode.passkey_invalid
    assert exc.value.status == 422
    assert await _reasons(world, "auth.passkey_add_failed") == [reason]


async def test__register__limit_reached__refused(kit: PasskeyKit, world: World) -> None:
    user = await world.add_user()
    for _ in range(PASSKEY_LIMIT):
        await kit.register(user)

    code = await _code(kit.start_registration().execute(user.id, await kit.session(user), PARTY))

    assert code is IdentityErrorCode.passkey_limit


async def test__register__disabled_or_no_party__refused(kit: PasskeyKit, world: World) -> None:
    user = await world.add_user()
    session = await kit.session(user)
    assert await _code(kit.start_registration().execute(user.id, session, None)) is IdentityErrorCode.passkeys_disabled

    await world.settings.set(KEY_PASSKEYS_ENABLED, False, source="admin")
    code = await _code(kit.start_registration().execute(user.id, session, PARTY))

    assert code is IdentityErrorCode.passkeys_disabled


async def test__login__valid_assertion__opens_session(kit: PasskeyKit, world: World) -> None:
    user = await world.add_user()
    passkey = await kit.register(user, name="Телефон")
    previous = "old-secret"
    old = await world.sessions.get(await kit.session(user))
    assert old is not None
    await world.sessions.add(replace(old, id_hash=hash_token(previous)))
    world.clock.advance(minutes=1)

    result = await kit.finish_login().execute(
        PARTY, await kit.login_response(), ip="1.2.3.4", user_agent="UA", previous_secret=previous
    )

    assert result.user.id == user.id
    assert result.session.id_hash == hash_token(result.secret)
    assert await world.sessions.get(hash_token(previous)) is None
    assert result.user.last_login_at == world.clock.now
    used = (await kit.passkeys.list_for_user(user.id))[0]
    assert used.sign_count == 1
    assert used.last_used_at == world.clock.now
    login = [e for e in (await _entries(world)) if e.action == "auth.login"]
    assert [e.details for e in login] == [{"ip": "1.2.3.4", "method": "passkey", "device": passkey.name}]


async def test__login__options__no_allow_list_and_uv_required(kit: PasskeyKit) -> None:
    options = await kit.start_login().execute(PARTY)

    assert options["allowCredentials"] == []
    assert options["userVerification"] == "required"
    assert options["rpId"] == "studio.test"


async def test__login__replayed_assertion__rejected(kit: PasskeyKit, world: World) -> None:
    user = await world.add_user()
    await kit.register(user)
    response = await kit.login_response()
    await kit.finish_login().execute(PARTY, response)

    assert await _code(kit.finish_login().execute(PARTY, response)) is IdentityErrorCode.passkey_invalid
    assert await _reasons(world, "auth.passkey_login_failed") == ["challenge"]


async def test__login__counter_not_increasing__rejected_as_clone(kit: PasskeyKit, world: World) -> None:
    user = await world.add_user()
    await kit.register(user)
    await kit.finish_login().execute(PARTY, await kit.login_response())
    await kit.finish_login().execute(PARTY, await kit.login_response())

    clone = await kit.login_response(sign_count=1)

    assert await _code(kit.finish_login().execute(PARTY, clone)) is IdentityErrorCode.passkey_invalid
    assert await _reasons(world, "auth.passkey_login_failed") == ["sign_count"]
    assert (await kit.passkeys.list_for_user(user.id))[0].sign_count == 2


async def test__login__synced_passkey_with_zero_counter__accepted_every_time(kit: PasskeyKit, world: World) -> None:
    kit.phone = SoftAuthenticator(counter=False, synced=True)
    user = await world.add_user()
    passkey = await kit.register(user)
    assert passkey.backup_eligible
    assert passkey.backed_up

    for _ in range(3):
        await kit.finish_login().execute(PARTY, await kit.login_response())

    assert (await kit.passkeys.list_for_user(user.id))[0].sign_count == 0


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (UserStatus.disabled, IdentityErrorCode.account_disabled),
        (UserStatus.pending_approval, IdentityErrorCode.pending_approval),
        (UserStatus.pending_verification, IdentityErrorCode.email_not_verified),
    ],
)
async def test__login__account_cannot_sign_in__refused(
    kit: PasskeyKit, world: World, status: UserStatus, code: IdentityErrorCode
) -> None:
    user = await world.add_user()
    await kit.register(user)
    await world.users.update(replace(user, status=status))

    assert await _code(kit.finish_login().execute(PARTY, await kit.login_response())) is code
    assert not [e for e in (await _entries(world)) if e.action == "auth.login"]


async def test__login__deleted_key__unknown_credential(kit: PasskeyKit, world: World) -> None:
    user = await world.add_user()
    passkey = await kit.register(user)
    await kit.passkeys.delete(user.id, passkey.id)

    assert (
        await _code(kit.finish_login().execute(PARTY, await kit.login_response())) is IdentityErrorCode.passkey_invalid
    )
    assert await _reasons(world, "auth.passkey_login_failed") == ["unknown_credential"]


async def test__login__user_handle_of_someone_else__rejected(kit: PasskeyKit, world: World) -> None:
    user = await world.add_user()
    await kit.register(user)

    response = await kit.login_response(user_handle=b"u2")

    assert await _code(kit.finish_login().execute(PARTY, response)) is IdentityErrorCode.passkey_invalid
    assert await _reasons(world, "auth.passkey_login_failed") == ["user_handle"]


@pytest.mark.parametrize(
    ("tamper", "reason"),
    [({"origin": "https://phish.test"}, "signature"), ({"uv": False}, "user_verification")],
    ids=["phishing_origin", "no_user_verification"],
)
async def test__login__bad_assertion__rejected(
    kit: PasskeyKit, world: World, tamper: dict[str, object], reason: str
) -> None:
    user = await world.add_user()
    await kit.register(user)

    response = await kit.login_response(**tamper)

    assert await _code(kit.finish_login().execute(PARTY, response)) is IdentityErrorCode.passkey_invalid
    assert await _reasons(world, "auth.passkey_login_failed") == [reason]


async def test__login__key_of_old_domain__rejected(kit: PasskeyKit, world: World) -> None:
    user = await world.add_user()
    await kit.register(user)
    moved = RelyingParty(id="new.test", name="HSE Doc Studio", origin="https://new.test")

    options = await kit.start_login().execute(moved)
    response = kit.phone.get(options, origin="https://new.test")

    assert await _code(kit.finish_login().execute(moved, response)) is IdentityErrorCode.passkey_invalid


async def test__login__disabled_by_admin__refused(kit: PasskeyKit, world: World) -> None:
    await world.settings.set(KEY_PASSKEYS_ENABLED, False, source="admin")

    assert await _code(kit.start_login().execute(PARTY)) is IdentityErrorCode.passkeys_disabled


async def test__login__malformed_credential__passkey_invalid(kit: PasskeyKit, world: World) -> None:
    assert await _code(kit.finish_login().execute(PARTY, {"id": "x"})) is IdentityErrorCode.passkey_invalid
    assert await _reasons(world, "auth.passkey_login_failed") == ["malformed"]


async def test__reauth__own_passkey__opens_window(kit: PasskeyKit, world: World) -> None:
    user = await world.add_user()
    await kit.register(user)
    session = await kit.session(user, minutes_ago=30)

    options = await kit.start_reauth().execute(user.id, PARTY)
    until = await kit.reauth_uc().execute(user.id, session, PARTY, credential=kit.phone.get(options))

    assert _ids(options, "allowCredentials") == [kit.phone.credentials[0].id]
    assert until == world.clock.now + timedelta(minutes=10)
    assert (await world.sessions.get(session)).reauth_at == world.clock.now  # type: ignore[union-attr]
    assert await kit.start_registration().execute(user.id, session, PARTY)


async def test__reauth__key_of_another_person__rejected(kit: PasskeyKit, world: World) -> None:
    ann = await world.add_user()
    bob = await world.add_user("bob@example.org", user_id="u2")
    await kit.register(ann)
    bob_phone = SoftAuthenticator()
    await kit.register(bob, phone=bob_phone)
    session = await kit.session(ann, minutes_ago=30)

    options = await kit.start_reauth().execute(ann.id, PARTY)
    code = await _code(kit.reauth_uc().execute(ann.id, session, PARTY, credential=bob_phone.get(options)))

    assert code is IdentityErrorCode.passkey_invalid
    assert (await world.sessions.get(session)).reauth_at is None  # type: ignore[union-attr]


async def test__reauth__wrong_password__refused_and_audited(kit: PasskeyKit, world: World) -> None:
    user = await world.add_user()
    session = await kit.session(user, minutes_ago=30)

    code = await _code(kit.reauth_uc().execute(user.id, session, PARTY, password="wrong password"))

    assert code is IdentityErrorCode.invalid_credentials
    assert [e.action for e in (await _entries(world))] == ["auth.reauth_failed"]


async def test__reauth__password_disabled_by_admin__refused(kit: PasskeyKit, world: World) -> None:
    user = await world.add_user()
    await world.settings.set(KEY_PASSWORD_ENABLED, False, source="admin")
    session = await kit.session(user, minutes_ago=30)

    code = await _code(kit.reauth_uc().execute(user.id, session, PARTY, password=PASSWORD))

    assert code is IdentityErrorCode.invalid_credentials


async def test__reauth__session_of_another_person__forbidden(kit: PasskeyKit, world: World) -> None:
    ann = await world.add_user()
    bob = await world.add_user("bob@example.org", user_id="u2")
    session = await kit.session(bob)

    assert (
        await _code(kit.reauth_uc().execute(ann.id, session, PARTY, password=PASSWORD)) is IdentityErrorCode.forbidden
    )


async def test__start_reauth__no_own_keys__not_found(kit: PasskeyKit, world: World) -> None:
    user = await world.add_user()

    assert await _code(kit.start_reauth().execute(user.id, PARTY)) is IdentityErrorCode.not_found


async def test__delete__last_way_to_sign_in__refused(kit: PasskeyKit, world: World) -> None:
    user = await kit.without_password(await world.add_user())
    passkey = await kit.register(user)
    session = await kit.session(user)

    code = await _code(kit.delete_uc().execute(user.id, session, passkey.id))

    assert code is IdentityErrorCode.last_login_method
    assert await kit.passkeys.list_for_user(user.id) == [passkey]


async def test__delete__second_key_or_password_remains__removed(kit: PasskeyKit, world: World) -> None:
    user = await kit.without_password(await world.add_user())
    first = await kit.register(user)
    second = await kit.register(user, phone=SoftAuthenticator())
    session = await kit.session(user)

    await kit.delete_uc().execute(user.id, session, first.id)

    assert await kit.passkeys.list_for_user(user.id) == [second]
    assert (await _entries(world))[-1].action == "auth.passkey_removed"


async def test__delete__keys_disabled_by_admin_do_not_count(kit: PasskeyKit, world: World) -> None:
    user = await kit.without_password(await world.add_user())
    first = await kit.register(user)
    await kit.register(user, phone=SoftAuthenticator())
    await world.settings.set(KEY_PASSKEYS_ENABLED, False, source="admin")

    code = await _code(kit.delete_uc().execute(user.id, await kit.session(user), first.id))

    assert code is IdentityErrorCode.last_login_method


async def test__delete__stale_session__needs_reauth(kit: PasskeyKit, world: World) -> None:
    user = await world.add_user()
    passkey = await kit.register(user)

    code = await _code(kit.delete_uc().execute(user.id, await kit.session(user, minutes_ago=11), passkey.id))

    assert code is IdentityErrorCode.reauth_required


async def test__delete__key_of_another_person__not_found(kit: PasskeyKit, world: World) -> None:
    ann = await world.add_user()
    bob = await world.add_user("bob@example.org", user_id="u2")
    passkey = await kit.register(ann)

    assert (
        await _code(kit.delete_uc().execute(bob.id, await kit.session(bob), passkey.id)) is IdentityErrorCode.not_found
    )


async def test__rename__own_key__renamed_other__not_found(kit: PasskeyKit, world: World) -> None:
    ann = await world.add_user()
    await world.add_user("bob@example.org", user_id="u2")
    passkey = await kit.register(ann)

    renamed = await kit.rename_uc().execute(ann.id, passkey.id, " Рабочий ключ ")

    assert renamed.name == "Рабочий ключ"
    assert await _code(kit.rename_uc().execute("u2", passkey.id, "чужой")) is IdentityErrorCode.not_found
    assert await _code(kit.rename_uc().execute(ann.id, passkey.id, "   ")) is IdentityErrorCode.input_invalid


async def test__list__shows_password_and_policy(kit: PasskeyKit, world: World) -> None:
    user = await world.add_user()
    await kit.register(user)

    view = await kit.list_uc().execute(user.id)

    assert len(view.items) == 1
    assert view.has_password is True
    assert view.enabled is True


async def test__unlink_oidc__passkey_remains__allowed(kit: PasskeyKit, world: World) -> None:
    user = await kit.without_password(await world.add_user())
    await world.users.add_identity(UserIdentity(user.id, "sso", "sub-1", user.email, True))
    unlink = UnlinkOidcIdentityUC(
        world.users, world.creds, world.settings_service(), world.audit, world.uow, kit.passkeys
    )
    assert await _code(unlink.execute(user.id, "sso")) is IdentityErrorCode.last_login_method

    await kit.register(user)
    await unlink.execute(user.id, "sso")

    assert await world.users.list_identities(user.id) == []


def _admin() -> Actor:
    return Actor(kind=ActorKind.user, id="adm", source=ActorSource.session, is_instance_admin=True)


async def test__admin_reset__removes_every_key_and_audits(kit: PasskeyKit, world: World) -> None:
    user = await world.add_user()
    await kit.register(user)
    await kit.register(user, phone=SoftAuthenticator())

    assert len(await kit.list_admin_uc().execute(_admin(), user.id)) == 2
    removed = await kit.reset_admin_uc().execute(_admin(), user.id)

    assert removed == 2
    assert await kit.passkeys.list_for_user(user.id) == []
    reset = (await _entries(world))[-1]
    assert (reset.action, reset.actor_id, reset.target, reset.details) == (
        "admin.passkeys_reset",
        "adm",
        user.id,
        {"count": 2},
    )


async def test__admin_reset__not_admin__not_found(kit: PasskeyKit, world: World) -> None:
    user = await world.add_user()
    member = Actor(kind=ActorKind.user, id=user.id, source=ActorSource.session)

    assert await _code(kit.reset_admin_uc().execute(member, user.id)) is IdentityErrorCode.not_found
    assert await _code(kit.list_admin_uc().execute(member, user.id)) is IdentityErrorCode.not_found


async def _invite(world: World, token: str = "inv-token", email: str | None = "new@example.org") -> str:
    await world.invites.add(
        RegistrationInvite(
            token_hash=hash_token(token),
            email=email,
            created_by="adm",
            expires_at=world.clock.now + timedelta(days=3),
            id=f"inv-{token}",
        )
    )
    return token


async def test__signup_by_invite__account_without_password_key_and_session(kit: PasskeyKit, world: World) -> None:
    token = await _invite(world)

    options = await kit.start_signup().execute(PARTY, token, "Новый Человек")
    result = await kit.finish_signup().execute(
        PARTY, token, "Новый Человек", kit.phone.create(options), passkey_name="Chrome · macOS", ip="1.2.3.4"
    )

    user = result.user
    assert options["user"]["name"] == "new@example.org"  # type: ignore[index]
    assert kit.phone.credentials[0].user_handle == user.id.encode()
    assert (user.email, user.status, user.email_verified, user.name) == (
        "new@example.org",
        UserStatus.active,
        True,
        "Новый Человек",
    )
    assert await world.creds.get_hash(user.id) is None
    assert [p.name for p in await kit.passkeys.list_for_user(user.id)] == ["Chrome · macOS"]
    assert await world.sessions.get(result.session.id_hash) == result.session
    assert (await world.invites.get(hash_token(token))).used_at == world.clock.now  # type: ignore[union-attr]
    actions = [e.action for e in await _entries(world)]
    assert actions == ["auth.register", "auth.passkey_added", "auth.login"]

    # Тем же ключом человек входит дальше без пароля.
    login = await kit.finish_login().execute(PARTY, await kit.login_response())
    assert login.user.id == user.id


async def test__signup__invite_without_address__refused(kit: PasskeyKit, world: World) -> None:
    token = await _invite(world, email=None)

    assert await _code(kit.start_signup().execute(PARTY, token, "X")) is IdentityErrorCode.invitation_invalid


async def test__signup__address_already_has_account__email_taken(kit: PasskeyKit, world: World) -> None:
    await world.add_user("new@example.org")
    token = await _invite(world)

    assert await _code(kit.start_signup().execute(PARTY, token, "X")) is IdentityErrorCode.email_taken


async def test__signup__used_or_unknown_invite__refused(kit: PasskeyKit, world: World) -> None:
    token = await _invite(world)
    options = await kit.start_signup().execute(PARTY, token, "X")
    await kit.finish_signup().execute(PARTY, token, "X", kit.phone.create(options))

    assert await _code(kit.start_signup().execute(PARTY, token, "X")) in {
        IdentityErrorCode.invitation_invalid,
        IdentityErrorCode.email_taken,
    }
    assert await _code(kit.start_signup().execute(PARTY, "nope", "X")) is IdentityErrorCode.invitation_invalid


async def test__signup__challenge_of_another_invite__rejected(kit: PasskeyKit, world: World) -> None:
    first = await _invite(world, "first", "a@example.org")
    second = await _invite(world, "second", "b@example.org")
    options = await kit.start_signup().execute(PARTY, first, "A")

    code = await _code(kit.finish_signup().execute(PARTY, second, "B", kit.phone.create(options)))

    assert code is IdentityErrorCode.passkey_invalid
    assert await world.users.get_by_email("b@example.org") is None
    assert await _reasons(world, "auth.passkey_signup_failed") == ["challenge"]


async def test__signup__without_user_verification__rejected_and_invite_kept(kit: PasskeyKit, world: World) -> None:
    token = await _invite(world)
    options = await kit.start_signup().execute(PARTY, token, "X")

    code = await _code(kit.finish_signup().execute(PARTY, token, "X", kit.phone.create(options, uv=False)))

    assert code is IdentityErrorCode.passkey_invalid
    assert (await world.invites.get(hash_token(token))).used_at is None  # type: ignore[union-attr]


async def test__signup__passkeys_disabled__refused(kit: PasskeyKit, world: World) -> None:
    token = await _invite(world)
    await world.settings.set(KEY_PASSKEYS_ENABLED, False, source="admin")

    assert await _code(kit.start_signup().execute(PARTY, token, "X")) is IdentityErrorCode.passkeys_disabled


async def test__register_key__mail_to_owner_when_smtp(kit: PasskeyKit, world: World) -> None:
    world.sender = FakeSender(enabled=True)
    user = await world.add_user()

    await kit.register(user, name="Телефон")

    assert [(to, subject) for to, subject, _ in world.sender.sent] == [(user.email, "Добавлен passkey")]
    assert "«Телефон»" in world.sender.sent[0][2]


async def test__register_key__no_smtp__no_mail_but_audit(kit: PasskeyKit, world: World) -> None:
    user = await world.add_user()

    await kit.register(user)

    assert world.sender.sent == []
    assert "auth.passkey_added" in [e.action for e in await _entries(world)]


async def test__admin_reset__mail_with_count_only_when_keys_removed(kit: PasskeyKit, world: World) -> None:
    world.sender = FakeSender(enabled=True)
    user = await world.add_user()
    await kit.register(user)
    await kit.register(user, phone=SoftAuthenticator())
    world.sender.sent.clear()

    await kit.reset_admin_uc().execute(_admin(), user.id)
    await kit.reset_admin_uc().execute(_admin(), user.id)

    assert len(world.sender.sent) == 1
    to, subject, body = world.sender.sent[0]
    assert (to, subject) == (user.email, "Администратор сбросил ваши passkey")
    assert "ключей: 2" in body
