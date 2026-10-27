from __future__ import annotations

from datetime import timedelta

import pytest
from hse_doc_studio.core.identity.entities import UserStatus
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import hash_token
from hse_doc_studio.use_cases.identity.change_password import ChangePasswordUC
from hse_doc_studio.use_cases.identity.sessions import (
    ListSessionsUC,
    LogoutUC,
    RevokeOtherSessionsUC,
    RevokeSessionUC,
)

from .conftest import World

PASSWORD = "correct horse battery"


async def _login(world: World, email: str = "ann@example.org"):  # type: ignore[no-untyped-def]
    return await world.login_uc().execute(email, PASSWORD)


async def test_resolve_slides_idle_but_not_past_absolute(world: World) -> None:
    await world.add_user()
    login = await _login(world)
    service = world.service()
    created = world.clock.now
    for _ in range(4):
        world.clock.advance(days=6)
        resolved = await service.resolve(login.secret)
        assert resolved is not None
        assert resolved.session.expires_at == min(world.clock.now + world.policy.idle, created + world.policy.absolute)
    world.clock.advance(days=6)
    assert await service.resolve(login.secret) is None
    assert await world.sessions.get(login.session.id_hash) is None


async def test_resolve_idle_expiry(world: World) -> None:
    await world.add_user()
    login = await _login(world)
    world.clock.advance(days=7, seconds=1)
    assert await world.service().resolve(login.secret) is None


async def test_resolve_absolute_expiry_even_if_expires_at_is_later(world: World) -> None:
    await world.add_user()
    login = await _login(world)
    world.clock.advance(days=30)
    await world.sessions.touch(login.session.id_hash, world.clock.now, world.clock.now + timedelta(days=7))
    assert await world.service().resolve(login.secret) is None


async def test_resolve_does_not_write_within_touch_interval(world: World) -> None:
    await world.add_user()
    login = await _login(world)
    world.clock.advance(minutes=1)
    resolved = await world.service().resolve(login.secret)
    assert resolved is not None
    assert resolved.session.last_seen_at == login.session.last_seen_at


@pytest.mark.parametrize("secret", ["", "garbage"])
async def test_resolve_unknown_secret(world: World, secret: str) -> None:
    assert await world.service().resolve(secret) is None


async def test_resolve_rejects_disabled_user(world: World) -> None:
    user = await world.add_user()
    login = await _login(world)
    await world.users.update(
        type(user)(**{**user.__dict__, "status": UserStatus.disabled}),
    )
    assert await world.service().resolve(login.secret) is None


async def test_logout_is_idempotent(world: World) -> None:
    await world.add_user()
    login = await _login(world)
    uc = LogoutUC(world.sessions, world.audit)
    await uc.execute(login.secret)
    await uc.execute(login.secret)
    await uc.execute("")
    assert await world.service().resolve(login.secret) is None
    assert [e.action for e in await world.audit.list(action="auth.logout")] == ["auth.logout"]


async def test_list_and_revoke(world: World) -> None:
    await world.add_user()
    await world.add_user("bob@example.org", user_id="u2")
    mine = await _login(world)
    other = await _login(world)
    bobs = await _login(world, "bob@example.org")
    listed = await ListSessionsUC(world.sessions, world.clock).execute("u1", mine.session.id_hash)
    assert {(i.session.id_hash, i.current) for i in listed} == {
        (mine.session.id_hash, True),
        (other.session.id_hash, False),
    }
    revoke = RevokeSessionUC(world.sessions, world.audit)
    with pytest.raises(IdentityError) as exc:
        await revoke.execute("u1", bobs.session.id_hash)
    assert exc.value.code is IdentityErrorCode.forbidden
    await revoke.execute("u1", other.session.id_hash)
    assert await world.sessions.get(other.session.id_hash) is None
    assert await world.sessions.get(bobs.session.id_hash) is not None


async def test_revoke_others_keeps_current(world: World) -> None:
    await world.add_user()
    mine = await _login(world)
    await _login(world)
    await _login(world)
    assert await RevokeOtherSessionsUC(world.sessions, world.audit).execute("u1", mine.session.id_hash) == 2
    assert [s.id_hash for s in await world.sessions.list_for_user("u1")] == [mine.session.id_hash]


async def test_change_password_revokes_other_sessions_only(world: World) -> None:
    await world.add_user()
    await world.add_user("bob@example.org", user_id="u2")
    mine = await _login(world)
    await _login(world)
    bobs = await _login(world, "bob@example.org")
    uc: ChangePasswordUC = world.change_uc()
    revoked = await uc.execute("u1", mine.session.id_hash, PASSWORD, "a brand new passphrase")
    assert revoked == 1
    assert [s.id_hash for s in await world.sessions.list_for_user("u1")] == [mine.session.id_hash]
    assert await world.sessions.get(bobs.session.id_hash) is not None
    assert world.store.hashes["u1"] == "v2:a brand new passphrase"
    entry = (await world.audit.list(action="auth.password_changed"))[0]
    assert entry.details == {"revoked_sessions": 1}
    assert "passphrase" not in str(await world.audit.list())


async def test_change_password_rejects_wrong_current_and_weak_new(world: World) -> None:
    await world.add_user()
    mine = await _login(world)
    uc = world.change_uc()
    with pytest.raises(IdentityError) as exc:
        await uc.execute("u1", mine.session.id_hash, "not my password", "a brand new passphrase")
    assert exc.value.code is IdentityErrorCode.invalid_credentials
    with pytest.raises(IdentityError) as exc:
        await uc.execute("u1", mine.session.id_hash, PASSWORD, "short")
    assert exc.value.code is IdentityErrorCode.password_policy
    assert world.store.hashes["u1"] == f"v2:{PASSWORD}"
    assert hash_token(mine.secret) == mine.session.id_hash
