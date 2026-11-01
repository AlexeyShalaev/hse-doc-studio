from __future__ import annotations

import pytest
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.vcs.errors import ProfileInvalidError
from hse_doc_studio.use_cases.identity.account_profile import (
    UNSET,
    GetAccountUC,
    UpdateAccountInput,
    UpdateAccountUC,
)

from .conftest import World

DOMAIN = "noreply.studio.test"


def _update(world: World) -> UpdateAccountUC:
    return UpdateAccountUC(world.users, world.audit, world.uow, DOMAIN)


async def test_get_gives_the_noreply_identity_by_default(world: World) -> None:
    await world.add_user()

    view = await GetAccountUC(world.users, DOMAIN).execute("u1")

    assert (view.identity.name, view.identity.email, view.identity.is_noreply) == ("Ann", f"u1@{DOMAIN}", True)


async def test_get_unknown_user_is_auth_required(world: World) -> None:
    with pytest.raises(IdentityError) as caught:
        await GetAccountUC(world.users, DOMAIN).execute("ghost")

    assert caught.value.code is IdentityErrorCode.auth_required


async def test_update_keeps_the_fields_that_were_not_sent(world: World) -> None:
    await world.add_user()

    await _update(world).execute("u1", UpdateAccountInput(commit_name="A. Ivanova"))
    view = await _update(world).execute("u1", UpdateAccountInput(locale="en"))

    assert (view.user.name, view.user.locale, view.user.commit_name) == ("Ann", "en", "A. Ivanova")
    assert view.identity.name == "A. Ivanova"


async def test_own_address_and_opt_in_are_applied_and_audited(world: World) -> None:
    await world.add_user()

    own = await _update(world).execute("u1", UpdateAccountInput(commit_email="Ann@Home.Example"))
    opt_in = await _update(world).execute("u1", UpdateAccountInput(commit_email=None, commit_use_account_email=True))

    assert own.identity.email == "Ann@home.example"
    assert (opt_in.identity.email, opt_in.identity.is_noreply) == ("ann@example.org", False)
    assert len(await world.audit.list(action="account.profile_updated")) == 2


async def test_blank_commit_fields_reset_to_the_defaults(world: World) -> None:
    await world.add_user()
    await _update(world).execute("u1", UpdateAccountInput(commit_name="X Y", commit_email="x@y.example"))

    view = await _update(world).execute("u1", UpdateAccountInput(commit_name="  ", commit_email=None))

    assert (view.user.commit_name, view.user.commit_email, view.identity.is_noreply) == (None, None, True)


async def test_invalid_values_are_all_reported_under_their_own_field(world: World) -> None:
    await world.add_user()

    with pytest.raises(ProfileInvalidError) as caught:
        await _update(world).execute(
            "u1", UpdateAccountInput(name="   ", commit_name="<b>", commit_email="no-at-sign", locale="de")
        )

    assert {(e.field, e.code) for e in caught.value.errors} == {
        ("name", "name_required"),
        ("commit_name", "commit_name_invalid"),
        ("commit_email", "commit_email_invalid"),
        ("locale", "locale_invalid"),
    }
    user = await world.users.get("u1")
    assert user is not None
    assert (user.name, user.commit_name) == ("Ann", None)


async def test_nothing_changed_writes_no_audit(world: World) -> None:
    await world.add_user()

    await _update(world).execute("u1", UpdateAccountInput(name=UNSET))

    assert await world.audit.list(action="account.profile_updated") == []
