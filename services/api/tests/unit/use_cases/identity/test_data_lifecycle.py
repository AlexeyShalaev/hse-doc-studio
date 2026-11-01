"""Удаление человека, выгрузка его данных, сроки хранения."""

from __future__ import annotations

from dataclasses import replace

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.entities import UserStatus
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.lifecycle import DeletionBlockers, RetentionPolicy, pseudonym_for
from hse_doc_studio.use_cases.admin.lifecycle import DeleteUserUC, ExportMyDataUC, GetRetentionUC

from tests.fakes.lifecycle import InMemoryUserLifecycle
from tests.unit.use_cases.identity.conftest import World

ADMIN = Actor.user("boss", is_instance_admin=True)


async def _admin(world: World) -> None:
    await world.add_user("boss@example.org", user_id="boss")
    world.store.users["boss"] = replace(world.store.users["boss"], is_instance_admin=True)


def _uc(world: World) -> tuple[DeleteUserUC, InMemoryUserLifecycle]:
    lifecycle = InMemoryUserLifecycle(world.store)
    return DeleteUserUC(world.users, lifecycle, world.audit, world.uow), lifecycle


async def _fails(coro: object, code: IdentityErrorCode) -> None:
    with pytest.raises(IdentityError) as err:
        await coro  # type: ignore[misc]
    assert err.value.code is code


async def test__delete_user__disabled_without_projects__erased_and_audited_by_pseudonym(world: World) -> None:
    await _admin(world)
    user = await world.add_user(user_id="u1", status=UserStatus.disabled)
    delete, lifecycle = _uc(world)

    await delete.execute(ADMIN, user.id)

    assert "u1" not in world.store.users
    assert lifecycle.erased == [("u1", pseudonym_for("u1"))]
    [event] = await world.audit.list(action="admin.user_deleted")
    assert event.target == pseudonym_for("u1") != "u1"
    assert event.actor_id == "boss"


async def test__delete_user__active_account__must_be_disabled_first(world: World) -> None:
    await _admin(world)
    await world.add_user(user_id="u1")
    delete, lifecycle = _uc(world)

    await _fails(delete.execute(ADMIN, "u1"), IdentityErrorCode.user_not_disabled)

    assert "u1" in world.store.users
    assert lifecycle.erased == []


@pytest.mark.parametrize("blockers", [DeletionBlockers(projects=1), DeletionBlockers(orgs=1)], ids=["project", "org"])
async def test__delete_user__sole_owner__refused(world: World, blockers: DeletionBlockers) -> None:
    await _admin(world)
    await world.add_user(user_id="u1", status=UserStatus.disabled)
    delete, lifecycle = _uc(world)
    lifecycle.owned_projects["u1"] = blockers.projects
    lifecycle.sole_orgs["u1"] = blockers.orgs

    await _fails(delete.execute(ADMIN, "u1"), IdentityErrorCode.user_has_projects)

    assert "u1" in world.store.users
    assert await world.audit.list(action="admin.user_deleted") == []


async def test__delete_user__self_or_unknown_or_not_admin__refused(world: World) -> None:
    await _admin(world)
    await world.add_user(user_id="u1", status=UserStatus.disabled)
    delete, _ = _uc(world)

    await _fails(delete.execute(ADMIN, "boss"), IdentityErrorCode.forbidden)
    await _fails(delete.execute(ADMIN, "ghost"), IdentityErrorCode.not_found)
    await _fails(delete.execute(Actor.user("u1"), "u1"), IdentityErrorCode.not_found)


async def test__export__own_data_only__audited(world: World) -> None:
    user = await world.add_user(user_id="u1")
    export = ExportMyDataUC(InMemoryUserLifecycle(world.store), world.audit)

    data = await export.execute(Actor.user(user.id))

    assert data["profile"] == {"id": "u1", "email": user.email}
    assert [e.actor_id for e in await world.audit.list(action="account.data_exported")] == ["u1"]
    await _fails(export.execute(Actor.guest("link")), IdentityErrorCode.auth_required)


async def test__retention__admin_only(world: World) -> None:
    policy = RetentionPolicy(audit_days=365, deleted_projects_days=30, unused_blobs_days=14)

    assert await GetRetentionUC(policy).execute(ADMIN) == policy
    await _fails(GetRetentionUC(policy).execute(Actor.user("u1")), IdentityErrorCode.not_found)
