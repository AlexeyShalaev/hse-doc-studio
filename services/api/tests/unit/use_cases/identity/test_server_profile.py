from __future__ import annotations

from collections.abc import Iterator

import pytest
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.vcs.errors import ProfileInvalidError
from hse_doc_studio.use_cases.identity.account_profile import UpdateAccountUC
from hse_doc_studio.use_cases.profile.server_profile import ServerClearProfileUC, ServerUpdateProfileUC
from hse_doc_studio.use_cases.profile.update_profile import UpdateProfileInput

from .conftest import World

DOMAIN = "noreply.studio.test"


@pytest.fixture(autouse=True)
def _actor() -> Iterator[None]:
    set_current_actor(Actor.user("u1", "Ann", f"u1@{DOMAIN}"))
    yield
    set_current_actor(None)


async def test_put_profile_writes_the_account_commit_identity_and_delete_forgets_it(world: World) -> None:
    await world.add_user()
    accounts = UpdateAccountUC(world.users, world.audit, world.uow, DOMAIN)

    saved = await ServerUpdateProfileUC(accounts).execute(UpdateProfileInput(name="A. Ivanova", email="a@home.example"))
    cleared = await ServerClearProfileUC(accounts).execute()

    assert (saved.effective.name, saved.effective.email) == ("A. Ivanova", "a@home.example")
    assert (cleared.effective.name, cleared.effective.email) == ("Ann", f"u1@{DOMAIN}")
    user = await world.users.get("u1")
    assert user is not None
    assert (user.commit_name, user.commit_email) == (None, None)


async def test_put_profile_with_a_bad_address_keeps_the_profile_error(world: World) -> None:
    await world.add_user()
    accounts = UpdateAccountUC(world.users, world.audit, world.uow, DOMAIN)

    with pytest.raises(ProfileInvalidError):
        await ServerUpdateProfileUC(accounts).execute(UpdateProfileInput(name="Ann", email="nope"))
