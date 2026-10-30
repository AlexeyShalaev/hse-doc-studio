"""Админские сценарии над людьми: список, отключение, роль, одобрение, повторное приглашение."""

from __future__ import annotations

from dataclasses import replace

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.entities import Session, UserQuery, UserStatus
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import hash_token
from hse_doc_studio.core.listing import Window
from hse_doc_studio.use_cases.admin.invitations import ResendInviteUC
from hse_doc_studio.use_cases.admin.users import (
    ApproveUserUC,
    DisableUserUC,
    EnableUserUC,
    GetUserUC,
    ListApprovalsUC,
    ListUsersUC,
    RejectUserUC,
    RevokeUserSessionsUC,
    SetUserAdminUC,
)

from tests.fakes.identity import InMemoryUserDirectory
from tests.unit.use_cases.identity.conftest import T0, World

ADMIN = Actor.user("boss", is_instance_admin=True)


async def _admin(world: World) -> None:
    await world.add_user("boss@example.org", user_id="boss")
    world.store.users["boss"] = replace(world.store.users["boss"], is_instance_admin=True)


def _directory(world: World) -> InMemoryUserDirectory:
    return InMemoryUserDirectory(world.store)


async def _fails(coro: object, code: IdentityErrorCode) -> None:
    with pytest.raises(IdentityError) as err:
        await coro  # type: ignore[misc]
    assert err.value.code is code


async def test__list_users__search_and_status_filter_and_paging(world: World) -> None:
    await _admin(world)
    await world.add_user("anna@example.org", user_id="u1")
    await world.add_user("maria@example.org", user_id="u2", status=UserStatus.pending_approval)
    directory = _directory(world)
    directory.project_counts["u1"] = 3

    found = await ListUsersUC(directory).execute(ADMIN, UserQuery(q="ANNA"))
    pending = await ListUsersUC(directory).execute(ADMIN, UserQuery(statuses=(UserStatus.pending_approval,)))
    page = await ListUsersUC(directory).execute(ADMIN, UserQuery(window=Window(limit=1, offset=1)))

    assert [(x.user.id, x.project_count) for x in found.items] == [("u1", 3)]
    assert [x.user.id for x in pending.items] == ["u2"]
    assert (len(page.items), page.total) == (1, 3)


async def test__list_users__not_an_admin__refused(world: World) -> None:
    await _fails(
        ListUsersUC(_directory(world)).execute(Actor.user("u1"), UserQuery()),
        IdentityErrorCode.not_found,
    )


async def test__get_user__unknown__not_found(world: World) -> None:
    await _admin(world)

    await _fails(GetUserUC(_directory(world)).execute(ADMIN, "ghost"), IdentityErrorCode.not_found)


async def test__disable_user__closes_sessions_and_audits(world: World) -> None:
    await _admin(world)
    user = await world.add_user()
    await world.sessions.add(Session(hash_token("s"), user.id, "c", T0, T0, T0 + world.policy.idle))

    await DisableUserUC(world.users, world.sessions, world.audit, world.uow).execute(ADMIN, user.id)

    assert world.store.users[user.id].status is UserStatus.disabled
    assert await world.sessions.list_for_user(user.id) == []
    assert [e.target for e in await world.audit.list(action="admin.user_disabled")] == [user.id]


async def test__disable_user__last_admin__protected(world: World) -> None:
    await _admin(world)

    await _fails(
        DisableUserUC(world.users, world.sessions, world.audit, world.uow).execute(ADMIN, "boss"),
        IdentityErrorCode.last_admin,
    )
    assert world.store.users["boss"].status is UserStatus.active


async def test__set_admin__last_admin_cannot_be_demoted_but_second_admin_can(world: World) -> None:
    await _admin(world)
    change = SetUserAdminUC(world.users, world.audit, world.uow)
    await _fails(change.execute(ADMIN, "boss", is_admin=False), IdentityErrorCode.last_admin)

    await world.add_user("deputy@example.org", user_id="u2")
    await change.execute(ADMIN, "u2", is_admin=True)
    await change.execute(ADMIN, "boss", is_admin=False)

    assert world.store.users["u2"].is_instance_admin
    assert not world.store.users["boss"].is_instance_admin


async def test__enable_user__only_disabled_come_back(world: World) -> None:
    await _admin(world)
    gone = await world.add_user(user_id="u1", status=UserStatus.disabled)
    waiting = await world.add_user("w@example.org", user_id="u2", status=UserStatus.pending_approval)
    enable = EnableUserUC(world.users, world.audit, world.uow)

    await enable.execute(ADMIN, gone.id)
    await _fails(enable.execute(ADMIN, waiting.id), IdentityErrorCode.not_found)

    assert world.store.users[gone.id].status is UserStatus.active
    assert world.store.users[waiting.id].status is UserStatus.pending_approval


async def test__revoke_sessions__counts_and_audits(world: World) -> None:
    await _admin(world)
    user = await world.add_user()
    for name in ("a", "b"):
        await world.sessions.add(Session(hash_token(name), user.id, "c", T0, T0, T0 + world.policy.idle))
    revoke = RevokeUserSessionsUC(world.users, world.sessions, world.audit, world.uow)

    assert await revoke.execute(ADMIN, user.id) == 2
    await _fails(revoke.execute(ADMIN, "ghost"), IdentityErrorCode.not_found)


async def test__approve__moves_pending_approval_to_active(world: World) -> None:
    await _admin(world)
    waiting = await world.add_user("w@example.org", user_id="u2", status=UserStatus.pending_approval)
    approve = ApproveUserUC(world.users, world.audit, world.uow)

    queue = await ListApprovalsUC(_directory(world)).execute(ADMIN, UserQuery())
    approved = await approve.execute(ADMIN, waiting.id)

    assert [x.user.id for x in queue.items] == [waiting.id]
    assert approved.status is UserStatus.active
    assert (await ListApprovalsUC(_directory(world)).execute(ADMIN, UserQuery())).total == 0
    await _fails(approve.execute(ADMIN, waiting.id), IdentityErrorCode.not_found)


async def test__reject__disables_and_only_for_pending(world: World) -> None:
    await _admin(world)
    waiting = await world.add_user("w@example.org", user_id="u2", status=UserStatus.pending_approval)
    active = await world.add_user("a@example.org", user_id="u3")
    reject = RejectUserUC(world.users, world.audit, world.uow)

    await reject.execute(ADMIN, waiting.id)
    await _fails(reject.execute(ADMIN, active.id), IdentityErrorCode.not_found)

    assert world.store.users[waiting.id].status is UserStatus.disabled
    assert world.store.users[active.id].status is UserStatus.active


async def test__resend_invite__old_link_dies_new_one_has_same_address(world: World) -> None:
    await _admin(world)
    created = await world.create_invite_uc().execute(ADMIN, email="new@example.org")
    resend = ResendInviteUC(world.invites, world.create_invite_uc(), world.audit, world.uow)

    again = await resend.execute(ADMIN, created.invite.id)

    assert again.invite.email == "new@example.org"
    assert again.invite.id != created.invite.id
    assert await world.invites.get(created.invite.token_hash) is None
    assert again.link is not None
    assert again.link != created.link
    await _fails(resend.execute(ADMIN, created.invite.id), IdentityErrorCode.not_found)
