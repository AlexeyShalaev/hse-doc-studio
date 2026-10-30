from __future__ import annotations

from dataclasses import replace

import pytest
from hse_doc_studio.core.identity.entities import UserStatus
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import hash_token
from hse_doc_studio.core.identity.session_policy import login_delay

from .conftest import World

PASSWORD = "correct horse battery"


async def _fail(world: World, email: str, password: str = "wrong password!") -> IdentityError:
    with pytest.raises(IdentityError) as exc:
        await world.login_uc().execute(email, password, ip="1.2.3.4")
    return exc.value


async def test_login_creates_session_and_audit(world: World) -> None:
    await world.add_user()
    result = await world.login_uc().execute(" Ann@Example.org ", PASSWORD, ip="1.2.3.4", user_agent="UA")
    assert result.session.id_hash == hash_token(result.secret)
    assert await world.sessions.get(result.session.id_hash) == result.session
    assert result.session.expires_at == world.clock.now + world.policy.idle
    assert result.session.csrf_token
    assert (await world.users.get("u1")).last_login_at == world.clock.now  # type: ignore[union-attr]
    assert [e.action for e in await world.audit.list()] == ["auth.login"]


async def test_unknown_email_is_indistinguishable_and_still_hashes(world: World) -> None:
    await world.add_user()
    before = world.hasher.verify_calls
    unknown = await _fail(world, "nobody@example.org")
    unknown_calls = world.hasher.verify_calls - before
    before = world.hasher.verify_calls
    wrong = await _fail(world, "ann@example.org")
    known_calls = world.hasher.verify_calls - before
    assert unknown.code is wrong.code is IdentityErrorCode.invalid_credentials
    assert unknown.detail == wrong.detail
    assert unknown_calls == known_calls == 1


async def test_failed_login_unknown_email__audit_keeps_no_typed_value(world: World) -> None:
    await world.add_user()
    typed = "My$ecretPassw0rd-pasted-by-mistake"

    await _fail(world, typed)
    await _fail(world, "ann@example.org")

    known, unknown = (e.details for e in await world.audit.list(action="auth.login_failed"))
    assert known == {"ip": "1.2.3.4", "email": "ann@example.org"}
    assert typed not in str(unknown)
    assert set(unknown) == {"ip", "email_hash"}


async def test_user_without_password_gets_same_error(world: World) -> None:
    user = await world.add_user()
    world.store.hashes.pop(user.id)
    err = await _fail(world, user.email, PASSWORD)
    assert err.code is IdentityErrorCode.invalid_credentials


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (UserStatus.pending_verification, IdentityErrorCode.email_not_verified),
        (UserStatus.pending_approval, IdentityErrorCode.pending_approval),
        (UserStatus.disabled, IdentityErrorCode.account_disabled),
    ],
)
async def test_status_is_revealed_only_after_correct_password(world: World, status: UserStatus, code) -> None:  # type: ignore[no-untyped-def]
    await world.add_user(status=status)
    assert (await _fail(world, "ann@example.org")).code is IdentityErrorCode.invalid_credentials
    with pytest.raises(IdentityError) as exc:
        await world.login_uc().execute("ann@example.org", PASSWORD)
    assert exc.value.code is code
    assert await world.sessions.list_for_user("u1") == []


async def test_rehash_on_login_when_params_changed(world: World) -> None:
    await world.add_user()
    world.store.hashes["u1"] = f"v1:{PASSWORD}"
    await world.login_uc().execute("ann@example.org", PASSWORD)
    assert world.store.hashes["u1"] == f"v2:{PASSWORD}"


async def test_login_rotates_previous_session(world: World) -> None:
    await world.add_user()
    first = await world.login_uc().execute("ann@example.org", PASSWORD)
    second = await world.login_uc().execute("ann@example.org", PASSWORD, previous_secret=first.secret)
    assert first.secret != second.secret
    assert await world.sessions.get(first.session.id_hash) is None
    assert await world.sessions.get(second.session.id_hash) is not None


async def test_progressive_delay_and_reset(world: World) -> None:
    await world.add_user()
    for _ in range(5):
        await _fail(world, "ann@example.org")
    err = await _fail(world, "ann@example.org", PASSWORD)
    assert err.code is IdentityErrorCode.rate_limited
    assert err.retry_after_s == 1
    world.clock.advance(seconds=1)
    await world.login_uc().execute("ann@example.org", PASSWORD, ip="1.2.3.4")
    assert await world.attempts.get("login:ann@example.org|1.2.3.4") is None


async def test_delay_survives_restart_and_is_never_a_permanent_block(world: World) -> None:
    await world.add_user()
    for _ in range(8):
        await _fail(world, "ann@example.org")
    # «Перезапуск»: новый экземпляр сценария поверх того же хранилища попыток видит прежнюю задержку.
    err = await _fail(world, "ann@example.org", PASSWORD)
    assert err.code is IdentityErrorCode.rate_limited
    assert err.retry_after_s is not None
    world.clock.advance(seconds=err.retry_after_s)
    await world.login_uc().execute("ann@example.org", PASSWORD, ip="1.2.3.4")


def test_login_delay_grows_to_cap() -> None:
    seconds = [login_delay(n).total_seconds() for n in (1, 4, 5, 6, 7, 30)]
    assert seconds == [0, 0, 1, 2, 4, 900]


async def test_user_disabled_during_password_check_is_denied_and_not_resurrected(world: World) -> None:
    await world.add_user()
    verify = world.hasher.verify

    def verify_then_disable(password: str, stored: str) -> bool:
        ok = verify(password, stored)
        # админ отключает пользователя, пока идёт проверка пароля
        world.store.users["u1"] = replace(world.store.users["u1"], status=UserStatus.disabled)
        return ok

    world.hasher.verify = verify_then_disable  # type: ignore[method-assign]

    err = await _fail(world, "ann@example.org", PASSWORD)

    assert err.code is IdentityErrorCode.account_disabled
    assert world.store.users["u1"].status is UserStatus.disabled
    assert await world.sessions.list_for_user("u1") == []


async def test_login_keeps_changes_made_during_password_check(world: World) -> None:
    await world.add_user()
    verify = world.hasher.verify

    def verify_then_promote(password: str, stored: str) -> bool:
        ok = verify(password, stored)
        world.store.users["u1"] = replace(world.store.users["u1"], is_instance_admin=True)
        return ok

    world.hasher.verify = verify_then_promote  # type: ignore[method-assign]

    result = await world.login_uc().execute("ann@example.org", PASSWORD, ip="1.2.3.4")

    assert result.user.is_instance_admin
    assert world.store.users["u1"].is_instance_admin
