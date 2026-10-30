"""Связывание внешнего входа с аккаунтами и JIT: защита от захвата аккаунта и матрица режимов регистрации."""

from __future__ import annotations

from dataclasses import replace

import pytest
from hse_doc_studio.core.identity.auth_settings import (
    KEY_PASSWORD_ENABLED,
    KEY_REGISTRATION_DOMAINS,
    KEY_REGISTRATION_MODE,
    KEY_REQUIRE_APPROVAL,
)
from hse_doc_studio.core.identity.entities import RegistrationMode, UserIdentity, UserStatus
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.oidc import OidcErrorCode, OidcLoginError, OidcProviderConfig
from hse_doc_studio.use_cases.identity.oidc_identities import ListOidcIdentitiesUC, UnlinkOidcIdentityUC
from hse_doc_studio.use_cases.identity.oidc_login import CompleteOidcLoginUC, StartOidcLoginUC

from tests.fixtures.fake_oidc import CLIENT_ID, CLIENT_SECRET, ISSUER
from tests.unit.use_cases.identity.conftest import World
from tests.unit.use_cases.identity.test_oidc_login import REDIRECT, _Catalog, _Flow


def _flow(world: World, *, auto_provision: bool = False) -> _Flow:
    flow = _Flow(world)
    provider = OidcProviderConfig("sso", "SSO", ISSUER, CLIENT_ID, CLIENT_SECRET, auto_provision=auto_provision)
    catalog = _Catalog(provider)
    flow.start = StartOidcLoginUC(catalog, flow.start._client, flow.codec, world.clock)  # noqa: SLF001
    flow.complete = CompleteOidcLoginUC(
        catalog, flow.complete._client, flow.codec, world.users, world.sessions,  # noqa: SLF001
        world.audit, world.uow, world.policy, world.clock, auth_settings=world.settings_service(),
    )  # fmt: skip
    return flow


async def _login(flow: _Flow, **claims: object):  # type: ignore[no-untyped-def]
    started = await flow.start.execute("sso", redirect_uri=REDIRECT, next_path="/x")
    code, state = flow.idp.authorize(started.authorize_url, **claims)
    return await flow.finish(started.sealed_state, state, code)


async def _set_mode(world: World, mode: RegistrationMode, **extra: object) -> None:
    await world.settings.set(KEY_REGISTRATION_MODE, mode.value, source="test")
    for key, value in extra.items():
        await world.settings.set(key, value, source="test")


async def test_verified_email_links_to_existing_verified_account(world: World) -> None:
    await world.add_user()
    flow = _flow(world)

    result = await _login(flow, sub="new-sub", email="Ann@Example.org", email_verified=True)

    assert result.user.id == "u1"
    assert result.linked
    assert result.secret
    assert [i.subject for i in await world.users.list_identities("u1")] == ["new-sub"]
    assert any(e.action == "auth.oidc_link" for e in world.audit._entries)  # noqa: SLF001


@pytest.mark.parametrize("claims", [{"email": "ann@example.org", "email_verified": False}, {"email": None}])
async def test_unverified_provider_email_never_links_takeover(world: World, claims: dict[str, object]) -> None:
    await world.add_user()
    flow = _flow(world, auto_provision=True)

    with pytest.raises(OidcLoginError) as caught:
        await _login(flow, sub="attacker", **claims)

    assert caught.value.code is OidcErrorCode.email_unverified
    assert await world.users.list_identities("u1") == []
    assert not world.sessions._items  # noqa: SLF001


async def test_account_with_unverified_local_email_is_not_linked(world: World) -> None:
    user = await world.add_user()
    await world.users.update(replace(user, email_verified=False))
    flow = _flow(world)

    with pytest.raises(OidcLoginError) as caught:
        await _login(flow, sub="s", email="ann@example.org", email_verified=True)

    assert caught.value.code is OidcErrorCode.link_required
    assert await world.users.list_identities("u1") == []


async def test_disabled_account_is_not_linked_or_signed_in(world: World) -> None:
    await world.add_user(status=UserStatus.disabled)
    flow = _flow(world)

    with pytest.raises(OidcLoginError) as caught:
        await _login(flow, sub="s", email="ann@example.org", email_verified=True)

    assert caught.value.code is OidcErrorCode.account_denied
    assert await world.users.list_identities("u1") == []


async def test_identity_of_another_account_is_not_stolen_by_email(world: World) -> None:
    await world.add_user()
    other = await world.add_user("bob@example.org", user_id="u2")
    await world.users.add_identity(UserIdentity(other.id, "sso", "bobs-sub", "bob@example.org", True))
    flow = _flow(world)

    result = await _login(flow, sub="bobs-sub", email="ann@example.org", email_verified=True)

    assert result.user.id == "u2"


async def test_unknown_person_without_auto_provision_is_not_linked(world: World) -> None:
    flow = _flow(world)

    with pytest.raises(OidcLoginError) as caught:
        await _login(flow, sub="s", email="new@example.org", email_verified=True)

    assert caught.value.code is OidcErrorCode.not_linked
    assert await world.users.count() == 0


@pytest.mark.parametrize(
    ("mode", "domains", "expected"),
    [
        (RegistrationMode.open, None, "active"),
        (RegistrationMode.domains, ["example.org"], "active"),
        (RegistrationMode.domains, ["other.org"], OidcErrorCode.registration_denied),
        (RegistrationMode.invite, None, OidcErrorCode.registration_denied),
        (RegistrationMode.closed, None, OidcErrorCode.registration_denied),
    ],
)
async def test_jit_follows_registration_mode_matrix(
    world: World, mode: RegistrationMode, domains: list[str] | None, expected: object
) -> None:
    extra = {KEY_REGISTRATION_DOMAINS: domains} if domains else {}
    await _set_mode(world, mode, **extra)
    flow = _flow(world, auto_provision=True)

    if expected == "active":
        result = await _login(flow, sub="s", email="new@example.org", email_verified=True, name="New One")
        assert result.provisioned
        assert result.secret
        assert result.user.status is UserStatus.active
        assert result.user.email_verified
        assert result.user.name == "New One"
        assert [i.provider for i in await world.users.list_identities(result.user.id)] == ["sso"]
    else:
        with pytest.raises(OidcLoginError) as caught:
            await _login(flow, sub="s", email="new@example.org", email_verified=True)
        assert caught.value.code is expected
        assert await world.users.count() == 0


async def test_jit_with_approval_creates_pending_account_without_session(world: World) -> None:
    await _set_mode(world, RegistrationMode.open, **{KEY_REQUIRE_APPROVAL: True})
    flow = _flow(world, auto_provision=True)

    with pytest.raises(OidcLoginError) as caught:
        await _login(flow, sub="s", email="new@example.org", email_verified=True)

    assert caught.value.code is OidcErrorCode.pending_approval
    user = await world.users.get_by_email("new@example.org")
    assert user is not None
    assert user.status is UserStatus.pending_approval
    assert not world.sessions._items  # noqa: SLF001


async def test_profile_link_requires_the_same_session(world: World) -> None:
    await world.add_user()
    await world.add_user("bob@example.org", user_id="u2")
    flow = _flow(world)
    mine = await world.login_uc().execute("ann@example.org", "correct horse battery")
    theirs = await world.login_uc().execute("bob@example.org", "correct horse battery")

    async def attempt(secret: str | None):  # type: ignore[no-untyped-def]
        started = await flow.start.execute("sso", redirect_uri=REDIRECT, next_path="/s", link_user_id="u1")
        code, state = flow.idp.authorize(started.authorize_url, sub="x", email="whatever@else.org")
        return await flow.complete.execute(
            "sso", sealed_state=started.sealed_state, state=state, code=code, error=None, previous_secret=secret
        )

    for bad in (None, theirs.secret):
        with pytest.raises(OidcLoginError) as caught:
            await attempt(bad)
        assert caught.value.code is OidcErrorCode.state_invalid
    result = await attempt(mine.secret)

    assert result.linked
    assert result.secret is None
    assert result.session is None
    assert [i.subject for i in await world.users.list_identities("u1")] == ["x"]


async def test_profile_link_refuses_identity_owned_by_someone_else(world: World) -> None:
    await world.add_user()
    other = await world.add_user("bob@example.org", user_id="u2")
    await world.users.add_identity(UserIdentity(other.id, "sso", "bobs", None, False))
    flow = _flow(world)
    mine = await world.login_uc().execute("ann@example.org", "correct horse battery")
    started = await flow.start.execute("sso", redirect_uri=REDIRECT, next_path=None, link_user_id="u1")
    code, state = flow.idp.authorize(started.authorize_url, sub="bobs")

    with pytest.raises(OidcLoginError) as caught:
        await flow.complete.execute(
            "sso", sealed_state=started.sealed_state, state=state, code=code, error=None,
            previous_secret=mine.secret,
        )  # fmt: skip

    assert caught.value.code is OidcErrorCode.identity_taken


def _unlink(world: World) -> UnlinkOidcIdentityUC:
    return UnlinkOidcIdentityUC(world.users, world.creds, world.settings_service(), world.audit, world.uow)


async def test_unlink_keeps_password_login(world: World) -> None:
    await world.add_user()
    await world.users.add_identity(UserIdentity("u1", "sso", "s", None, False))

    await _unlink(world).execute("u1", "sso")

    assert await world.users.list_identities("u1") == []


async def test_cannot_unlink_the_last_login_method(world: World) -> None:
    await world.add_user()
    world.store.hashes.clear()
    await world.users.add_identity(UserIdentity("u1", "sso", "s", None, False))

    with pytest.raises(IdentityError) as caught:
        await _unlink(world).execute("u1", "sso")

    assert caught.value.code is IdentityErrorCode.last_login_method
    assert len(await world.users.list_identities("u1")) == 1


async def test_cannot_unlink_when_password_login_is_disabled(world: World) -> None:
    await world.add_user()
    await world.settings.set(KEY_PASSWORD_ENABLED, False, source="test")
    await world.users.add_identity(UserIdentity("u1", "sso", "s", None, False))

    with pytest.raises(IdentityError) as caught:
        await _unlink(world).execute("u1", "sso")

    assert caught.value.code is IdentityErrorCode.last_login_method


async def test_can_unlink_one_of_two_providers_without_password(world: World) -> None:
    await world.add_user()
    world.store.hashes.clear()
    await world.users.add_identity(UserIdentity("u1", "a", "s", None, False))
    await world.users.add_identity(UserIdentity("u1", "b", "s", None, False))

    await _unlink(world).execute("u1", "a")

    assert [i.provider for i in await world.users.list_identities("u1")] == ["b"]


async def test_unlink_unknown_provider_is_not_found(world: World) -> None:
    await world.add_user()

    with pytest.raises(IdentityError) as caught:
        await _unlink(world).execute("u1", "sso")

    assert caught.value.code is IdentityErrorCode.not_found


async def test_list_identities_labels_known_providers(world: World) -> None:
    await world.add_user()
    await world.users.add_identity(UserIdentity("u1", "sso", "s", "a@b.c", True))
    await world.users.add_identity(UserIdentity("u1", "gone", "s", None, False))
    flow = _flow(world)
    catalog = flow.start._catalog  # noqa: SLF001

    views = await ListOidcIdentitiesUC(world.users, catalog).execute("u1")

    assert [(v.identity.provider, v.label) for v in views] == [("gone", None), ("sso", "SSO")]


async def test_account_with_another_subject_of_the_same_provider_is_not_relinked(world: World) -> None:
    await world.add_user()
    await world.users.add_identity(UserIdentity("u1", "sso", "first", None, False))
    flow = _flow(world)

    with pytest.raises(OidcLoginError) as caught:
        await _login(flow, sub="second", email="ann@example.org", email_verified=True)

    assert caught.value.code is OidcErrorCode.identity_taken
    assert [i.subject for i in await world.users.list_identities("u1")] == ["first"]
